import os
import sys
import time
import logging
from http import HTTPStatus

import requests
import telebot
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

RETRY_PERIOD = 600
ENDPOINT = (
    "https://practicum.yandex.ru/api/"
    "user_api/homework_statuses/"
)
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}

HOMEWORK_VERDICTS = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = {
        "PRACTICUM_TOKEN": PRACTICUM_TOKEN,
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }
    missing = [key for key, value in tokens.items() if not value]
    if missing:
        logger.critical(
            "Отсутствуют обязательные переменные окружения: "
            f"{', '.join(missing)}"
        )
        return False
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'Бот отправил сообщение "{message}"')
        return True
    except telebot.apihelper.ApiException as error:
        logger.error(
            f"Сбой при отправке сообщения в Telegram: {error}"
        )
        return False


def get_api_answer(timestamp):
    """Делает запрос к API-сервису Practicum."""
    if not isinstance(timestamp, (int, float)):
        error_msg = "timestamp должен быть числом"
        logger.error(error_msg)
        raise TypeError(error_msg)

    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={"from_date": timestamp},
        )
        if response.status_code != HTTPStatus.OK:
            error_msg = (
                f"Эндпоинт недоступен (status={response.status_code}). "
                f"URL: {ENDPOINT}"
            )
            logger.error(error_msg)
            raise requests.exceptions.HTTPError(error_msg)
        return response.json()

    except requests.exceptions.ConnectionError as error:
        error_msg = (
            f"Ошибка соединения при запросе к API: {error}. "
            f"Проверьте доступность эндпоинта {ENDPOINT}"
        )
        logger.error(error_msg)
        raise Exception(error_msg)

    except requests.exceptions.RequestException as error:
        error_msg = (
            f"Ошибка при запросе к API: {error}. "
            f"URL: {ENDPOINT}, timestamp: {timestamp}"
        )
        logger.error(error_msg)
        raise Exception(error_msg)


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        error_msg = "Ответ API не является словарем"
        logger.error(error_msg)
        raise TypeError(error_msg)

    if "homeworks" not in response:
        error_msg = 'В ответе API отсутствует ключ "homeworks"'
        logger.error(error_msg)
        raise KeyError(error_msg)

    homeworks = response["homeworks"]
    if not isinstance(homeworks, list):
        error_msg = "В ответе API homeworks не является списком"
        logger.error(error_msg)
        raise TypeError(error_msg)

    return homeworks


def parse_status(homework):
    """Извлекает из информации о домашней работе статус."""
    if not isinstance(homework, dict):
        error_msg = "homework должен быть словарем"
        logger.error(error_msg)
        raise TypeError(error_msg)

    if "homework_name" not in homework:
        error_msg = 'В ответе API отсутствует ключ "homework_name"'
        logger.error(error_msg)
        raise KeyError(error_msg)

    if "status" not in homework:
        error_msg = 'В ответе API отсутствует ключ "status"'
        logger.error(error_msg)
        raise KeyError(error_msg)

    name = homework["homework_name"]
    status = homework["status"]

    if status not in HOMEWORK_VERDICTS:
        error_msg = f"Неожиданный статус домашней работы: {status}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    verdict = HOMEWORK_VERDICTS[status]
    return (
        f'Изменился статус проверки работы "{name}". '
        f"{verdict}"
    )


def check_homework_status(bot, timestamp):
    """Проверяет статус ДЗ и отправляет уведомление."""
    try:
        response = get_api_answer(timestamp)
        homeworks = check_response(response)
        if homeworks:
            message = parse_status(homeworks[0])
            send_message(bot, message)
        else:
            logger.debug("Отсутствие в ответе новых статусов")
        return response.get("current_date", timestamp)

    except Exception as error:
        message = f"Сбой в работе программы: {error}"
        logger.error(message)
        send_message(bot, message)
        return timestamp


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit(1)

    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        timestamp = check_homework_status(bot, timestamp)
        time.sleep(RETRY_PERIOD)


if __name__ == "__main__":
    main()
