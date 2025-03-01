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
        if isinstance(other, KeyboardButton):
            return self.text == other.text
        return NotImplemented

    def __str__(self) -> str:
        """Возвращает строковое представление кнопки."""
        return self.text

    def __repr__(self) -> str:
        """Возвращает более информативное представление для отладки."""
        return f"KeyboardText(text={self.text!r})"


# Кнопки, используемые в разных меню
BUTTON_BIND_WITH_TG_USER = KeyboardText(text="Связать с пользователем")
BUTTON_BIND_TO_YOURSELF = KeyboardText(text="Привязать к себе")

BUTTON_UNBIND_FROM_TG_USER = KeyboardText(text="Отвязать от пользователя")
BUTTON_UNBIND_FROM_YOURSELF = KeyboardText(text="Отвязать от себя")

BUTTON_CLOSE = KeyboardText(text="Закрыть")

BUTTON_OWN = KeyboardText(text="Свои")
BUTTON_WIREGUARD_USER = KeyboardText(text="Пользователя Wireguard")
BUTTON_TELEGRAM_USER = KeyboardText(text="Пользователя Telegram")

BUTTON_SELECT_TELEGRAM_USER = KeyboardText(text="Выбрать пользователя")
BUTTON_ENTER_TELEGRAM_ID = KeyboardText(text="Ввести TID")


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