import logging
from functools import wraps

from telegram import Update  # type: ignore
from telegram.ext import CallbackContext  # type: ignore

from libs.wireguard import config

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
        telegram_id = update.effective_user.id

        # Проверка на наличие прав администратора
        if telegram_id in config.telegram_admin_ids:
            return await func(update, context, *args, **kwargs)

        logger.info(
            "Пользователь с Tid [%s] пытался выполнить администраторскую команду.",
            telegram_id
        )
        if update.message:
            await update.message.reply_text("У вас нет прав для выполнения этой команды.")
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
        current_command = context.user_data.get("command")
        if current_command is not None:
            logger.info(
                "Попытка выполнить команду [%s] в процессе выполнения другой [%s].",
                update.message.text.lower(), current_command
            )
            if update.message:
                await update.message.reply_text(
                    f"Перед началом выполнения новой команды [{update.message.text.lower()}] "
                    f"завершите выполнение [{current_command}]."
                )
            return None

        return await func(update, context, *args, **kwargs)

    return wrapper
