import os
import telebot
import time
from datetime import datetime
from openai import OpenAI
import requests
from io import BytesIO
from loguru import logger
from pathlib import Path

# Настройка логирования с помощью Loguru
logger.remove()  # Удаляем стандартный обработчик
logger.add("bot_logs/bot_{time}.log", rotation="10 MB", compression="zip", backtrace=True, diagnose=True)
logger.add(lambda msg: print(msg), level="INFO",
           format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")

# Токены API (в реальном проекте следует использовать переменные окружения)
TELEGRAM_TOKEN = "7617140226:AAHxsSC3rlhMUPn7tNRDZltoK1vy4V35N8k"
OPENAI_API_KEY = "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"
ADMIN_ID = "5178922969"  # ID админа для отправки отчетов

# Инициализация OpenAI и Telegram бота
bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)


def get_local_image(prompt):
    """Если есть файл по ключу — возвращает BytesIO, иначе None"""
    prompt_to_filename = {
        "красный квадрат": "squares/красный_квадрат.png",
        "синий квадрат": "squares/синий_квадрат.png"
    }
    for key, filename in prompt_to_filename.items():
        if key in prompt.lower():
            full_path = Path(filename)
            if full_path.exists():
                logger.info(f"Используется локальное изображение: {full_path}")
                return BytesIO(full_path.read_bytes())
            else:
                logger.warning(f"Файл {full_path} не найден, хотя есть в словаре")
    return None


# Словарь для хранения истории запросов пользователей
user_history = {}


def generate_image(prompt):
    """Функция для генерации изображения с помощью DALL-E"""
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size="1024x1024"
        )

        image_url = response.data[0].url

        # Загружаем изображение
        image_response = requests.get(image_url)
        if image_response.status_code == 200:
            logger.info(f"Изображение успешно сгенерировано по запросу: '{prompt}'")
            return BytesIO(image_response.content)
        else:
            logger.error(f"Ошибка при загрузке изображения: {image_response.status_code}, запрос: '{prompt}'")
            return None
    except Exception as e:
        logger.exception(f"Ошибка при генерации изображения по запросу '{prompt}'")
        return None


def analyze_dialog(user_id):
    """Анализирует диалог с пользователем с помощью GPT-4o"""
    if user_id not in user_history or not user_history[user_id]:
        logger.warning(f"Попытка анализа пустой истории для пользователя {user_id}")
        return "История диалога пуста."

    try:
        logger.info(f"Начинаем анализ диалога для пользователя {user_id}")
        history_text = "\n".join([f"Время: {entry['time']}, Запрос: {entry['prompt']}"
                                  for entry in user_history[user_id]])

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system",
                 "content": "Ты - аналитический помощник. Проанализируй историю запросов пользователя и составь краткий отчет."},
                {"role": "user",
                 "content": f"История запросов пользователя:\n{history_text}\n\nСоставь краткий отчет о том, какие изображения запрашивал пользователь, в каком количестве и в какое время."}
            ]
        )
        logger.debug(f"Получен анализ от GPT-4o для пользователя {user_id}")
        return response.choices[0].message.content
    except Exception as e:
        logger.exception(f"Ошибка при анализе диалога для пользователя {user_id}")
        return f"Произошла ошибка при анализе диалога: {str(e)}"


def send_admin_report(user_id, username):
    """Отправляет отчет администратору о действиях пользователя"""
    if user_id not in user_history or not user_history[user_id]:
        logger.warning(f"Попытка отправки отчета с пустой историей для пользователя {user_id}")
        return

    logger.info(f"Подготовка отчета для администратора о пользователе {user_id} ({username})")
    user_info = f"Пользователь: {username} (ID: {user_id})"
    analysis = analyze_dialog(user_id)

    # Форматирование истории запросов
    history_text = "\n".join([f"• {entry['time']}: \"{entry['prompt']}\""
                              for entry in user_history[user_id]])

    report = f"📊 ОТЧЕТ О ДЕЙСТВИЯХ ПОЛЬЗОВАТЕЛЯ 📊\n\n{user_info}\n\n"
    report += f"📝 АНАЛИЗ:\n{analysis}\n\n"
    report += f"📜 ИСТОРИЯ ЗАПРОСОВ:\n{history_text}"

    try:
        bot.send_message(ADMIN_ID, report)
        logger.success(f"Отчет о пользователе {user_id} успешно отправлен администратору")
    except Exception as e:
        logger.exception(f"Ошибка при отправке отчета администратору о пользователе {user_id}")


# Обработчик команды /start
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"User_{user_id}"
    logger.info(f"Пользователь {username} (ID: {user_id}) запустил бота")

    bot.reply_to(message,
                 "👋 Привет! Я бот для генерации изображений.\n\n"
                 "Просто напиши, какое изображение ты хочешь получить, например:\n"
                 "• пришли мне красный квадрат\n"
                 "• пришли мне синий квадрат\n"
                 "• пришли мне Феррари\n\n"
                 "И я сгенерирую его для тебя!")


# Обработчик команды /report (только для админа)
@bot.message_handler(commands=['report'])
def handle_report(message):
    user_id = message.from_user.id

    if str(user_id) == ADMIN_ID:
        logger.info("Администратор запросил отчеты о пользователях")

        if not user_history:
            logger.info("История пользователей пуста")
            bot.reply_to(message, "Пока нет данных о пользователях.")
            return

        for user_id, history in user_history.items():
            try:
                username = bot.get_chat(user_id).username or f"User_{user_id}"
                send_admin_report(user_id, username)
            except Exception as e:
                logger.exception(f"Ошибка при обработке истории пользователя {user_id}")

        bot.reply_to(message, "Отчеты по всем пользователям отправлены.")
    else:
        logger.warning(f"Пользователь {user_id} пытался использовать команду администратора /report")
        bot.reply_to(message, "У вас нет доступа к этой команде.")


# Обработчик текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"User_{user_id}"
    prompt = message.text

    logger.info(f"Получен запрос от {username} (ID: {user_id}): '{prompt}'")

    # Создаем запись в истории пользователя, если её еще нет
    if user_id not in user_history:
        logger.debug(f"Создана новая запись истории для пользователя {user_id}")
        user_history[user_id] = []

    # Отправляем сообщение о начале обработки
    bot.send_message(message.chat.id, "🔄 Обрабатываю запрос, пожалуйста, подождите...")

    # Сначала проверяем, есть ли локальное изображение
    image_data = get_local_image(prompt)

    # Если локального изображения нет, генерируем новое
    if image_data is None:
        logger.info(f"Локальное изображение не найдено для '{prompt}', генерируем новое")
        image_data = generate_image(prompt)
    else:
        logger.info(f"Найдено готовое изображение для запроса: '{prompt}'")

    if image_data:
        # Отправляем изображение
        bot.send_photo(message.chat.id, image_data)
        logger.info(f"Изображение отправлено пользователю {user_id}")

        # Записываем информацию о запросе
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_history[user_id].append({
            'time': current_time,
            'prompt': prompt
        })
        logger.debug(f"Запрос добавлен в историю пользователя {user_id}, всего запросов: {len(user_history[user_id])}")

        # Если пользователь сделал 3 запроса, отправляем отчет админу
        if len(user_history[user_id]) % 3 == 0:
            logger.info(f"Пользователь {user_id} достиг {len(user_history[user_id])} запросов, отправляем отчет")
            send_admin_report(user_id, username)
    else:
        bot.send_message(message.chat.id,
                         "😞 К сожалению, не удалось обработать изображение. Пожалуйста, попробуйте другой запрос.")
        logger.warning(f"Не удалось обработать изображение для запроса пользователя {user_id}: '{prompt}'")


# Запуск бота
if __name__ == "__main__":
    # Создаем директорию для логов и изображений, если их не существует
    os.makedirs("bot_logs", exist_ok=True)
    os.makedirs("squares", exist_ok=True)

    # Проверяем наличие локальных изображений и предупреждаем, если их нет
    for image_name in ["красный_квадрат.png", "синий_квадрат.png"]:
        if not Path(f"squares/{image_name}").exists():
            logger.warning(f"Файл {image_name} не найден в папке squares. "
                           f"Изображения будут генерироваться через API.")

    logger.info("==========================================")
    logger.info("Бот запущен и готов к обработке сообщений")
    logger.info("==========================================")

    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logger.exception("Критическая ошибка в работе бота")