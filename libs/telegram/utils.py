import re
import logging
import asyncio
from typing import Iterable, List, Optional, Union

from telegram import Update
from telegram.ext import CallbackContext
from telegram.error import TelegramError

from libs.core import config


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


async def send_long_message(
    update: Update,
    message: str,
    max_length: int = config.telegram_max_message_length,
    parse_mode: Optional[str] = None,
) -> None:
    """
    Отправляет сообщение (или несколько), разбивая его на части, если оно превышает ограничение.

    Args:
        update (Update): Объект обновления Telegram.
        message (str): Текст, который нужно отправить.
        max_length (int, optional): Максимальное количество символов в одном сообщении.
        parse_mode (Optional[str], optional): Тип парсинга сообщения (Markdown, HTML и т.д.).
    """
    if not update.message:
        return

    for i in range(0, len(message), max_length):
        await update.message.reply_text(message[i : i + max_length], parse_mode=parse_mode)


async def send_batched_messages(
    update: Update,
    batched_lines: List[List[str]],
    parse_mode: Optional[str] = None,
    groups_before_delay: int = 2,
    delay_between_groups: float = 0.5
) -> None:
    """
    Отправляет сообщения батчами с задержками между группами

    Args:
        update (Update): Объект обновления Telegram
        batched_lines (List[List[str]]): Список строк с информацией о конфигах
        parse_mode (str): Тип парсинга (Markdown/HTML)
        groups_before_delay (int): Количество групп сообщений перед задержкой
        delay_between_groups (float): Задержка между группами сообщений
    """
    if not update.message or not batched_lines:
        return

    total_batches = len(batched_lines)
    sent_groups = 0

    for batch_idx, batch in enumerate(batched_lines, 1):
        # Формируем сообщение из текущего батча
        message = "\n".join(batch)
        
        try:
            await update.message.reply_text(message, parse_mode=parse_mode)
        except Exception as e:
            # Fallback: попытка отправить по частям если возникла ошибка
            await send_long_message(update, message, parse_mode=parse_mode)

        sent_groups += 1
        # Управление задержками между группами сообщений
        if sent_groups % groups_before_delay == 0 and batch_idx != total_batches:
            await asyncio.sleep(delay_between_groups)


async def get_username_by_id(telegram_id: int, context: CallbackContext) -> Optional[str]:
    """
    Возвращает @username пользователя по его Telegram ID.

    Args:
        telegram_id (int): Целочисленный Telegram ID пользователя.
        context (CallbackContext): Контекст бота для доступа к Bot API.

    Returns:
        Optional[str]: Строка вида "@username" или None, если имя не задано или пользователь не найден.
    """
    try:
        # Получаем информацию о чате по Telegram ID
        chat = await context.bot.get_chat(telegram_id)
        return f"@{chat.username}" if chat.username else None
    except TelegramError as e:
        logger.error(f"Ошибка при получении информации о пользователе {telegram_id}: {e}")
        return None


async def get_username_with_limit(
    telegram_id: int,
    context: CallbackContext,
    semaphore: asyncio.Semaphore
) -> Optional[str]:
    """
    Возвращает username пользователя, используя семафор для ограничения количества параллельных запросов.

    Args:
        telegram_id (int): Идентификатор пользователя Telegram.
        context (CallbackContext): Контекст бота для доступа к Bot API.
        semaphore (asyncio.Semaphore): Объект семафора для ограничения числа одновременных запросов.

    Returns:
        Optional[str]: Username вида "@имя" или None, если пользователь не найден/ошибка.
    """
    async with semaphore:  # Ограничиваем количество одновременно выполняемых запросов с помощью семафора
        # Выполняем запрос к Telegram API внутри семафора
        return await get_username_by_id(telegram_id, context)


async def get_usernames_in_bulk(
    telegram_ids: Iterable[int],
    context: CallbackContext,
    semaphore: asyncio.Semaphore
) -> dict[int, Optional[str]]:
    """
    Параллельно (с использованием семафора) получает username для списка Telegram ID.

    Args:
        telegram_ids (Iterable[int]): Итерабельный набор Telegram ID пользователей.
        context (CallbackContext): Контекст бота для доступа к Bot API.
        semaphore (asyncio.Semaphore): Семафор для ограничения параллельных запросов.

    Returns:
        dict[int, Optional[str]]: Словарь вида {telegram_id: "@username" или None}.
    """
    if not telegram_ids:
        return {}
    
    # Создаем задачи для асинхронного получения username 
    # с использованием ограничения на количество запросов
    tasks = [
        get_username_with_limit(tid, context, semaphore)
        for tid in telegram_ids
    ]
    # Выполняем все задачи параллельно с помощью asyncio.gather,
    # возвращая результаты как список
    usernames = await asyncio.gather(*tasks)
    return {
        tid: username
        for tid, username in zip(telegram_ids, usernames)
    }