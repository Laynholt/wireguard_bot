import logging
from dataclasses import dataclass

from telegram import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestUsers,
)

# Импорт вашего перечисления команд
from .commands import BotCommands

@dataclass(frozen=True)
class KeyboardText:
    """
    Класс для хранения текста кнопки в виде поля `text`.
    Объекты неизменяемы (frozen=True).
    """
    text: str

    def __eq__(self, other: object) -> bool:
        if isinstance(other, KeyboardText):
            return self.text == other.text
        if isinstance(other, str):
            return self.text == other
        return NotImplemented


# Кнопки, используемые в разных меню
BUTTON_BIND_TO_YOURSELF = KeyboardText(text="Привязать к себе")
BUTTON_UNBIND_FROM_YOURSELF = KeyboardText(text="Отвязать от себя")

BUTTON_CLOSE = KeyboardText(text="Закрыть")

BUTTON_OWN = KeyboardText(text="Свои")
BUTTON_WIREGUARD_USER_CONFIG = KeyboardText(text="Пользователя Wireguard")

BUTTON_WIREGUARD_USER_STATS = KeyboardText(text="Пользователя Wireguard")

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
            f"/{BotCommands.SHOW_BANNED_TELEGRAM_USER}",
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

# Меню для привязки пользователей (BIND_MENU)
BIND_MENU = ReplyKeyboardMarkup(
    [
        [
            KeyboardButton(
                text="Связать с пользователем",
                request_users=KeyboardButtonRequestUsers(
                    request_id=0,
                    user_is_bot=False,
                    request_username=True,
                ),
            ),
            BUTTON_BIND_TO_YOURSELF.text,
            BUTTON_CLOSE.text,
        ]
    ],
    one_time_keyboard=True,
)

# Меню для отвязки пользователей (UNBIND_MENU)
UNBIND_MENU = ReplyKeyboardMarkup(
    [
        [
            KeyboardButton(
                text="Отвязать от пользователя",
                request_users=KeyboardButtonRequestUsers(
                    request_id=0,
                    user_is_bot=False,
                    request_username=True,
                ),
            ),
            BUTTON_UNBIND_FROM_YOURSELF.text,
            BUTTON_CLOSE.text,
        ]
    ],
    one_time_keyboard=True,
)

# Меню для выбора, чью конфигурацию получить (CONFIG_MENU)
CONFIG_MENU = ReplyKeyboardMarkup(
    [
        [
            KeyboardButton(
                text="Пользователя Telegram",
                request_users=KeyboardButtonRequestUsers(
                    request_id=0,
                    user_is_bot=False,
                    request_username=True,
                ),
            ),
            BUTTON_WIREGUARD_USER_CONFIG.text,
        ],
        [
            BUTTON_OWN.text,
            BUTTON_CLOSE.text,
        ]
    ],
    one_time_keyboard=True,
)

# Меню для выбора, чьи привязки получить (BINDINGS_MENU)
BINDINGS_MENU = ReplyKeyboardMarkup(
    [
        [
            KeyboardButton(
                text="Пользователя Telegram",
                request_users=KeyboardButtonRequestUsers(
                    request_id=0,
                    user_is_bot=False,
                    request_username=True,
                ),
            ),
            BUTTON_OWN.text,
            BUTTON_CLOSE.text,
        ],
    ],
    one_time_keyboard=True,
)

SELECT_USER_MENU = ReplyKeyboardMarkup(
    [
        [
            KeyboardButton(
                text="Выбрать пользователя",
                request_users=KeyboardButtonRequestUsers(
                    request_id=0,
                    user_is_bot=False,
                    request_username=True,
                ),
            ),
            BUTTON_CLOSE.text,
        ]
    ],
    one_time_keyboard=True,
)

# Меню для выборка пользователя статистики
STATS_MENU = ReplyKeyboardMarkup(
    [
        [
            KeyboardButton(
                text="Пользователя Telegram",
                request_users=KeyboardButtonRequestUsers(
                    request_id=0,
                    user_is_bot=False,
                    request_username=True,
                ),
            ),
            BUTTON_WIREGUARD_USER_STATS.text,
        ],
        [
            BUTTON_CLOSE.text,
        ]
    ],
    one_time_keyboard=True,
)