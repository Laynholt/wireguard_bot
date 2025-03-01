from dataclasses import dataclass
from telegram import KeyboardButton


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