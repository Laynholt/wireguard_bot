from telegram import ReplyKeyboardMarkup

# Импорт вашего перечисления команд
from .keys import *
from libs.telegram.commands import BotCommand


ADMIN_MENU = ReplyKeyboardMarkup(
    (
        (
            f"/{BotCommand.ADD_USER.pretty_text}",
            f"/{BotCommand.REMOVE_USER.pretty_text}",
            f"/{BotCommand.COM_UNCOM_USER.pretty_text}",
            f"/{BotCommand.SHOW_USERS_STATE.pretty_text}",
        ),
        (
            f"/{BotCommand.BIND_USER.pretty_text}",
            f"/{BotCommand.UNBIND_USER.pretty_text}",
            f"/{BotCommand.UNBIND_TELEGRAM_ID.pretty_text}",
            f"/{BotCommand.GET_USERS_BY_ID.pretty_text}",
            f"/{BotCommand.SHOW_ALL_BINDINGS.pretty_text}",
        ),
        (
            f"/{BotCommand.BAN_TELEGRAM_USER.pretty_text}",
            f"/{BotCommand.UNBAN_TELEGRAM_USER.pretty_text}",
            f"/{BotCommand.REMOVE_TELEGRAM_USER.pretty_text}",
        ),
        (
            f"/{BotCommand.GET_CONFIG.pretty_text}",
            f"/{BotCommand.GET_QRCODE.pretty_text}",
            f"/{BotCommand.SEND_CONFIG.pretty_text}",
        ),
        (
            f"/{BotCommand.GET_TELEGRAM_ID.pretty_text}",
            f"/{BotCommand.GET_TELEGRAM_USERS.pretty_text}",
        ),
        (
            f"/{BotCommand.GET_MY_STATS.pretty_text}",
            f"/{BotCommand.GET_USER_STATS.pretty_text}",
            f"/{BotCommand.GET_ALL_STATS.pretty_text}",
        ),
        (
            f"/{BotCommand.SEND_MESSAGE.pretty_text}",
            f"/{BotCommand.HELP.pretty_text}",
        ),
        (
            f"/{BotCommand.RELOAD_WG_SERVER.pretty_text}",
        ),
    ),
    one_time_keyboard=True,
)

USER_MENU = ReplyKeyboardMarkup(
    (
        (
            f"/{BotCommand.GET_CONFIG.pretty_text}",
            f"/{BotCommand.GET_QRCODE.pretty_text}",
            f"/{BotCommand.REQUEST_NEW_CONFIG.pretty_text}",
        ),
        (
            f"/{BotCommand.GET_TELEGRAM_ID.pretty_text}",
            f"/{BotCommand.GET_MY_STATS.pretty_text}",
            f"/{BotCommand.HELP.pretty_text}",
        ),
    ),
    one_time_keyboard=True,
)
