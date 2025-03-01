import logging
from functools import wraps
from typing import Iterable

from telegram import Update
from telegram.ext import CallbackContext

from libs.core import config
from .types import TelegramId
from .utils import get_username_by_id

logger = logging.getLogger(__name__)


def admin_required(func):
    """
    Декоратор для проверки прав администратора у пользователя.

    Если пользователь не является администратором (не входит в список
    `config.telegram_admin_ids`), выводит сообщение о недостаточных правах.

    Args:
        func: Функция-обработчик Telegram-команды.

    Returns:
        Обёрнутую функцию, которая либо вызывает исходную
        функцию `func`, либо возвращает сообщение об ошибке.
    """
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        if update.effective_user is None:
            return None
        
        telegram_id = update.effective_user.id

        # Проверка на наличие прав администратора
        if telegram_id in config.telegram_admin_ids:
            return await func(update, context, *args, **kwargs)

        logger.info(
            "Пользователь с Tid [%s] пытался выполнить администраторскую команду.",
            telegram_id
        )
        if update.message:
            await update.message.reply_text(
                "⛔ <b>Ошибка:</b> У вас нет прав для выполнения этой команды.",
                parse_mode="HTML"
            )

        return None

    return wrapper


def command_lock(func):
    """
    Декоратор, не позволяющий вызывать новую команду, пока не завершена предыдущая.

    Если в `context.user_data` уже есть незавершённая команда, оповещает пользователя
    о необходимости сначала закончить её выполнение.

    Args:
        func: Функция-обработчик Telegram-команды.

    Returns:
        Обёрнутую функцию, которая либо вызывает исходную
        функцию `func`, либо выводит сообщение о необходимости
        завершить текущую команду.
    """
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        if context.user_data is None:
            return None
        
        current_command = context.user_data.get("command")
        if current_command is not None:
            if update.message is not None and update.message.text is not None:
                logger.info(
                    "Попытка выполнить команду [%s] в процессе выполнения другой [%s].",
                    update.message.text.lower(), current_command
                )
            if update.message is not None and update.message.text is not None:
                await update.message.reply_text(
                    f"Перед началом выполнения новой команды [{update.message.text.lower()}] "
                    f"завершите выполнение [{current_command}]."
                )
            return None

        return await func(update, context, *args, **kwargs)

    return wrapper


def check_user_not_blocked(allowed_ids: Iterable[TelegramId]):
    """
    Декоратор для проверки, разрешено ли использование команды пользователю.
    
    Если Telegram id пользователя отсутствует в множестве allowed_ids,
    считается, что пользователь заблокирован и ему не разрешается выполнение команды.
    
    Args:
        allowed_ids (Iterable[TelegramId]): Множество Telegram id, которые не заблокированы.
        
    Returns:
        Обёрнутую функцию, которая либо вызывает исходную функцию, либо отправляет сообщение о блокировке.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
            if update.effective_user is None:
                return None

            user_id = update.effective_user.id
            if user_id not in allowed_ids:
                text = (
                    update.message.text
                    if update.message is not None and update.message.text is not None
                    else ''
                )
                
                telegram_username = get_username_by_id(user_id, context)
                logger.info(
                    f'Обращение от заблокированного пользователя: {telegram_username} ({user_id}) '
                    f'с текстом: [{text}].'
                )
                
                # if update.message is not None:
                #     await update.message.reply_text(
                #         "Извините, вы заблокированы и не можете использовать эту команду."
                #     )
                return None

            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator