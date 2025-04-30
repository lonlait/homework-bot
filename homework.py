import os
import sys
import time
import logging
from http import HTTPStatus

import requests
import telebot
from dotenv import load_dotenv


load_dotenv()

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


class APIError(Exception):
    """Исключение при ошибке обращения к API."""


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = {
        "PRACTICUM_TOKEN": PRACTICUM_TOKEN,
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }
    missing = [key for key, value in tokens.items() if not value]
    if missing:
        error_msg = (
            "Отсутствуют обязательные переменные окружения: "
            f"{', '.join(missing)}"
        )
        logger.critical(error_msg)
        raise ValueError(error_msg)


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    if not hasattr(send_message, 'last_message'):
        send_message.last_message = None

    if message == send_message.last_message:
        logger.debug("Пропускаем отправку дублирующегося сообщения")
        return True

    logger.debug(f'Начинаю отправку сообщения: "{message}"')
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'Бот отправил сообщение "{message}"')
        send_message.last_message = message
        return True
    except (
        telebot.apihelper.ApiException,
        requests.exceptions.RequestException
    ) as error:
        logger.error(f"Сбой при отправке сообщения в Telegram: {error}")
        return False


def get_api_answer(timestamp):
    """Делает запрос к API-сервису Practicum."""
    logger.debug(
        "Отправляем запрос к API: "
        f"{ENDPOINT} с параметрами from_date={timestamp}"
    )
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={"from_date": timestamp},
        )
    except requests.exceptions.RequestException as error:
        error_msg = (
            f"Ошибка при запросе к API: {error}. "
            f"URL: {ENDPOINT}, timestamp: {timestamp}"
        )
        raise ConnectionError(error_msg)

    if response.status_code != HTTPStatus.OK:
        error_msg = (
            f"Эндпоинт недоступен (status={response.status_code}). "
            f"URL: {ENDPOINT}"
        )
        raise APIError(error_msg)

    logger.debug("Успешно получен ответ от API")
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    logger.debug("Начинаю проверку ответа API")
    if not isinstance(response, dict):
        error_msg = (
            f"Ответ API не является словарем, "
            f"получен тип {type(response).__name__}"
        )
        raise TypeError(error_msg)

    if "homeworks" not in response:
        error_msg = 'В ответе API отсутствует ключ "homeworks"'
        raise KeyError(error_msg)

    homeworks = response["homeworks"]
    if not isinstance(homeworks, list):
        error_msg = (
            f"В ответе API homeworks не является списком, "
            f"получен тип {type(homeworks).__name__}"
        )
        raise TypeError(error_msg)

    logger.debug("Проверка ответа API успешно завершена")
    return homeworks


def parse_status(homework):
    """Извлекает из информации о домашней работе статус."""
    logger.debug("Начинаю разбор статуса домашней работы")
    if not isinstance(homework, dict):
        error_msg = (
            f"homework должен быть словарем, "
            f"получен тип {type(homework).__name__}"
        )
        raise TypeError(error_msg)

    required_keys = ["homework_name", "status"]
    missing_keys = [key for key in required_keys if key not in homework]
    if missing_keys:
        error_msg = (
            f'В ответе API отсутствуют ключи: {", ".join(missing_keys)}'
        )
        raise KeyError(error_msg)

    name = homework["homework_name"]
    status = homework["status"]

    if status not in HOMEWORK_VERDICTS:
        error_msg = f"Неожиданный статус домашней работы: {status}"
        raise ValueError(error_msg)

    verdict = HOMEWORK_VERDICTS[status]
    message = (
        f'Изменился статус проверки работы "{name}". '
        f"{verdict}"
    )
    logger.debug("Разбор статуса домашней работы успешно завершен")
    return message


def check_homework_status(bot, timestamp):
    """Проверяет статус ДЗ и отправляет уведомление."""
    try:
        response = get_api_answer(timestamp)
        homeworks = check_response(response)
        if not homeworks:
            logger.debug("Отсутствие в ответе новых статусов")
            return timestamp

        message = parse_status(homeworks[0])
        if not send_message(bot, message):
            return timestamp

        return response.get("current_date", timestamp)

    except Exception as error:
        message = f"Сбой в работе программы: {error}"
        logger.error(message)
        send_message(bot, message)
        return timestamp


def main():
    """Основная логика работы бота."""
    try:
        check_tokens()
        bot = telebot.TeleBot(TELEGRAM_TOKEN)
        timestamp = int(time.time())

        while True:
            timestamp = check_homework_status(bot, timestamp)
            time.sleep(RETRY_PERIOD)
    except Exception as error:
        logger.error(f"Программа завершена с ошибкой: {error}")
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format=(
            "%(asctime)s [%(levelname)s] "
            "%(name)s:%(funcName)s:%(lineno)d - %(message)s"
        ),
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    main()
