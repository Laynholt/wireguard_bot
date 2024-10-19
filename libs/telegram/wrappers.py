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
        else:
            logger.info(f'Пользователь с Tid [{telegram_id}] пытался выполнить одну из команд администратора.')
            await update.message.reply_text('У вас нет прав для выполнения этой команды.')
            return None

    return wrapper