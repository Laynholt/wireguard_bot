import re
import logging
import asyncio
from typing import Iterable, Optional, Union

from telegram import Update# type: ignore
from telegram.ext import CallbackContext# type: ignore
from telegram.error import TelegramError# type: ignore

from libs.wireguard import config


logger = logging.getLogger(__name__)


def validate_username(username: str) -> bool:
    """
    Проверяет, соответствует ли имя пользователя разрешённым символам.
    
    Args:
        username (str): Имя пользователя.
        
    Returns:
        bool: True, если имя пользователя валидно, иначе False.
    """
    # Используем общий паттерн для проверки имени пользователя
    return re.match(f'^[{config.allowed_username_pattern}]+$', username) is not None


def validate_telegram_id(telegram_id: Union[str, int]) -> bool:
    """
    Проверяет, является ли Telegram ID числом.
    
    Args:
        telegram_id (str): Telegram ID.
        
    Returns:
        bool: True, если Telegram ID валидно, иначе False.
    """
    if isinstance(telegram_id, int):
        return True
    return telegram_id.isdigit() if isinstance(telegram_id, str) else False


async def send_long_message(update: Update, message: str, max_length: int = config.telegram_max_message_length, parse_mode = None):
    """
    Отправляем сообщение (или несколько, если оно длинное).
    Args:
        update (Update): Объект обновления Telegram.
        message (str): Сообщение.
        max_length (int, optional): Максимальная длина для разбивки.
        parse_mode (str, optional): Форматирование разметки (например, Markdown).
    """
    for i in range(0, len(message), max_length):
        await update.message.reply_text(message[i:i + max_length], parse_mode=parse_mode)


async def get_username_by_id(telegram_id: int, context: CallbackContext) -> Optional[str]:
    """
    Возвращает @username пользователя по его Telegram ID.
    
    Args:
        telegram_id (int): Telegram ID пользователя.

    Returns:
        str: @username пользователя, если он существует, или None, если пользователя нет или username отсутствует.
    """
    try:
        # Получаем информацию о чате по Telegram ID
        chat = await context.bot.get_chat(telegram_id)
        return f"@{chat.username}" if chat.username else None
    except TelegramError as e:
        logger.error(f"Ошибка при получении информации о пользователе {telegram_id}: {e}")
        return None


async def get_username_with_limit(telegram_id: int, context: CallbackContext, semaphore: asyncio.Semaphore):
    """
    Получает username пользователя по telegram_id, ограничивая количество одновременных запросов.

    Args:
        telegram_id (int): Идентификатор пользователя Telegram.
        context: Контекст, переданный в обработчик команд.

    Returns:
        str: Username пользователя или None, если имя не найдено.
    """
    async with semaphore:  # Ограничиваем количество одновременно выполняемых запросов с помощью семафора
        # Выполняем запрос к Telegram API внутри семафора
        return await get_username_by_id(telegram_id, context)


async def get_usernames_in_bulk(telegram_ids: Iterable[int], context: CallbackContext, semaphore: asyncio.Semaphore):
    """
    Получает username для списка пользователей, выполняя запросы параллельно с ограничением на количество одновременных запросов.

    Args:
        telegram_ids (list): Список идентификаторов пользователей Telegram.
        context: Контекст, переданный в обработчик команд.

    Returns:
        dict: Словарь, где ключ — telegram_id, а значение — username.
    """
    # Создаем задачи для асинхронного получения username с использованием ограничения на количество запросов
    tasks = [get_username_with_limit(telegram_id, context, semaphore) for telegram_id in telegram_ids]
    # Выполняем все задачи параллельно с помощью asyncio.gather, возвращая результаты как список
    usernames = await asyncio.gather(*tasks)
    return {telegram_id: username for telegram_id, username in zip(telegram_ids, usernames)}