from telegram import ReplyKeyboardMarkup

# Импорт вашего перечисления команд
from .keys import *
from libs.telegram.commands import BotCommands


# Админское меню (ADMIN_MENU)
ADMIN_MENU = ReplyKeyboardMarkup(
    [
        [
            f"/{BotCommands.ADD_USER}",
            f"/{BotCommands.REMOVE_USER}",
            f"/{BotCommands.COM_UNCOM_USER}",
            f"/{BotCommands.SHOW_USERS_STATE}",
        ],
        [
            f"/{BotCommands.BIND_USER}",
            f"/{BotCommands.UNBIND_USER}",
            f"/{BotCommands.UNBIND_TELEGRAM_ID}",
            f"/{BotCommands.GET_USERS_BY_ID}",
            f"/{BotCommands.SHOW_ALL_BINDINGS}",
        ],
        [
            f"/{BotCommands.BAN_TELEGRAM_USER}",
            f"/{BotCommands.UNBAN_TELEGRAM_USER}",
            f"/{BotCommands.REMOVE_TELEGRAM_USER}",
        ],
        [
            f"/{BotCommands.GET_CONFIG}",
            f"/{BotCommands.GET_QRCODE}",
            f"/{BotCommands.SEND_CONFIG}",
        ],
        [
            f"/{BotCommands.GET_TELEGRAM_ID}",
            f"/{BotCommands.GET_TELEGRAM_USERS}",
        ],
        [
            f"/{BotCommands.GET_MY_STATS}",
            f"/{BotCommands.GET_USER_STATS}",
            f"/{BotCommands.GET_ALL_STATS}",
        ],
        [
            f"/{BotCommands.SEND_MESSAGE}",
            f"/{BotCommands.HELP}",
        ],
        [
            f"/{BotCommands.RELOAD_WG_SERVER}"
        ]
    ],
    one_time_keyboard=True,
)

# Меню для обычных пользователей (USER_MENU)
USER_MENU = ReplyKeyboardMarkup(
    [
        [
            f"/{BotCommands.GET_CONFIG}",
            f"/{BotCommands.GET_QRCODE}",
            f"/{BotCommands.REQUEST_NEW_CONFIG}",
        ],
        [
            f"/{BotCommands.GET_TELEGRAM_ID}",
            f"/{BotCommands.GET_MY_STATS}",
            f"/{BotCommands.HELP}",
        ]
    ],
    one_time_keyboard=True,
)