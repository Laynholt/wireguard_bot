import logging
from functools import wraps

from telegram import Update# type: ignore
from telegram.ext import CallbackContext# type: ignore

from libs.wireguard import config

logger = logging.getLogger(__name__)


def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        telegram_id = update.effective_user.id

        # Проверка на наличие прав администратора
        if telegram_id in config.telegram_admin_ids:
            return await func(update, context, *args, **kwargs)
        
        logger.info(f'Пользователь с Tid [{telegram_id}] пытался выполнить одну из команд администратора.')
        await update.message.reply_text('У вас нет прав для выполнения этой команды.')
        return None

    return wrapper


def command_lock(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        if context.user_data['command'] is not None:
            logger.info(
                f'Попытка выполнить команду [{update.message.text.lower()}] в процессе '
                f'выполения другой [{context.user_data["command"]}].'
            )
            await update.message.reply_text(
                f'Перед началом выполнения новой команды [{update.message.text.lower()}]'
                f' завершите выполнение [{context.user_data["command"]}].'
            )
            return None
        return await func(update, context, *args, **kwargs)

    return wrapper