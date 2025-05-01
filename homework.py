import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telebot
from dotenv import load_dotenv

from decorators import prevent_duplicate_messages
from exceptions import APIError


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = (
    'https://practicum.yandex.ru/api/'
    'user_api/homework_statuses/'
)
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}


def check_tokens():
    """Проверяет доступность переменных окружения.

    Raises:
        ValueError: Если отсутствуют обязательные переменные окружения.
    """
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    missing = [key for key, value in tokens.items() if not value]
    if missing:
        logging.critical(
            'Отсутствуют обязательные переменные окружения: '
            f'{", ".join(missing)}'
        )
        raise ValueError(
            'Отсутствуют обязательные переменные окружения: '
            f'{", ".join(missing)}'
        )


@prevent_duplicate_messages
def send_message(bot, message):
    """Отправляет сообщение в Telegram чат.

    Args:
        bot: Объект бота Telegram.
        message: Текст сообщения для отправки.

    Returns:
        bool: True если сообщение отправлено успешно, False в случае ошибки.
    """
    logging.debug(f'Начинаю отправку сообщения: "{message}"')
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug(f'Бот отправил сообщение "{message}"')
        return True
    except (
        telebot.apihelper.ApiException,
        requests.exceptions.RequestException
    ) as error:
        logging.exception(f'Сбой при отправке сообщения в Telegram: {error}')
        return False


def get_api_answer(timestamp):
    """Делает запрос к API-сервису Practicum.

    Args:
        timestamp: Временная метка для запроса.

    Returns:
        dict: Ответ API в формате JSON.

    Raises:
        ConnectionError: При ошибке соединения с API.
        APIError: При недоступности эндпоинта.
    """
    logging.debug(
        'Отправляем запрос к API: '
        f'{ENDPOINT} с параметрами from_date={timestamp}'
    )
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp},
        )
    except requests.exceptions.RequestException as error:
        logging.exception(
            f'Ошибка при запросе к API: {error}. '
            f'URL: {ENDPOINT}, timestamp: {timestamp}'
        )
        raise ConnectionError(
            f'Ошибка при запросе к API: {error}. '
            f'URL: {ENDPOINT}, timestamp: {timestamp}'
        )

    if response.status_code != HTTPStatus.OK:
        logging.exception(
            f'Эндпоинт недоступен (status={response.status_code}). '
            f'URL: {ENDPOINT}'
        )
        raise APIError(
            f'Эндпоинт недоступен (status={response.status_code}). '
            f'URL: {ENDPOINT}'
        )

    logging.debug('Успешно получен ответ от API')
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации.

    Args:
        response: Ответ API для проверки.

    Returns:
        list: Список домашних работ.

    Raises:
        TypeError: При неверном типе данных в ответе.
        KeyError: При отсутствии необходимых ключей в ответе.
    """
    logging.debug('Начинаю проверку ответа API')
    if not isinstance(response, dict):
        logging.exception(
            'Ответ API не является словарем, '
            f'получен тип {type(response).__name__}'
        )
        raise TypeError(
            'Ответ API не является словарем, '
            f'получен тип {type(response).__name__}'
        )

    if 'homeworks' not in response:
        logging.exception('В ответе API отсутствует ключ "homeworks"')
        raise KeyError('В ответе API отсутствует ключ "homeworks"')

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        logging.exception(
            'В ответе API homeworks не является списком, '
            f'получен тип {type(homeworks).__name__}'
        )
        raise TypeError(
            'В ответе API homeworks не является списком, '
            f'получен тип {type(homeworks).__name__}'
        )

    logging.debug('Проверка ответа API успешно завершена')
    return homeworks


def parse_status(homework):
    """Извлекает из информации о домашней работе статус.

    Args:
        homework: Информация о домашней работе.

    Returns:
        str: Сообщение о статусе домашней работы.

    Raises:
        TypeError: При неверном типе данных.
        KeyError: При отсутствии необходимых ключей.
        ValueError: При неожиданном статусе работы.
    """
    logging.debug('Начинаю разбор статуса домашней работы')
    if not isinstance(homework, dict):
        logging.exception(
            'homework должен быть словарем, '
            f'получен тип {type(homework).__name__}'
        )
        raise TypeError(
            'homework должен быть словарем, '
            f'получен тип {type(homework).__name__}'
        )

    required_keys = ['homework_name', 'status']
    missing_keys = [key for key in required_keys if key not in homework]
    if missing_keys:
        logging.exception(
            f'В ответе API отсутствуют ключи: {", ".join(missing_keys)}'
        )
        raise KeyError(
            f'В ответе API отсутствуют ключи: {", ".join(missing_keys)}'
        )

    name = homework['homework_name']
    status = homework['status']

    if status not in HOMEWORK_VERDICTS:
        logging.exception(f'Неожиданный статус домашней работы: {status}')
        raise ValueError(f'Неожиданный статус домашней работы: {status}')

    verdict = HOMEWORK_VERDICTS[status]
    message = (
        f'Изменился статус проверки работы "{name}". '
        f'{verdict}'
    )
    logging.debug('Разбор статуса домашней работы успешно завершен')
    return message


def check_homework_status(bot, timestamp):
    """Проверяет статус ДЗ и отправляет уведомление.

    Args:
        bot: Объект бота Telegram.
        timestamp: Временная метка для запроса.

    Returns:
        int: Новая временная метка.
    """
    try:
        response = get_api_answer(timestamp)
        homeworks = check_response(response)
        if not homeworks:
            logging.debug('Отсутствие в ответе новых статусов')
            return timestamp

        message = parse_status(homeworks[0])
        if not send_message(bot, message):
            return timestamp

        return response.get('current_date', timestamp)

    except Exception as error:
        logging.exception(f'Сбой в работе программы: {error}')
        send_message(bot, f'Сбой в работе программы: {error}')
        return timestamp


def main():
    """Основная логика работы бота.

    Инициализирует бота и запускает бесконечный цикл проверки статуса
    домашних работ.
    """
    check_tokens()
    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        timestamp = check_homework_status(bot, timestamp)
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format=(
            '%(asctime)s [%(levelname)s] '
            '%(name)s:%(funcName)s:%(lineno)d - %(message)s'
        ),
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    main()
