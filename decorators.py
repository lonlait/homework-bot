import logging
from functools import wraps


def prevent_duplicate_messages(func):
    """Декоратор для предотвращения отправки дублирующихся сообщений."""
    last_message = None

    @wraps(func)
    def wrapper(*args, **kwargs):
        nonlocal last_message
        message = args[1]  # message is the second argument of send_message
        
        if message == last_message:
            logging.debug("Пропускаем отправку дублирующегося сообщения")
            return True
            
        result = func(*args, **kwargs)
        if result:  # Only update last_message if message was sent successfully
            last_message = message
        return result
        
    return wrapper 