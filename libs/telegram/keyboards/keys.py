from enum import Enum
from dataclasses import dataclass
from telegram import KeyboardButton


@dataclass(frozen=True)
class KeyText:
    """
    Класс для хранения текста кнопки в виде поля `text`.
    Объекты неизменяемы (frozen=True).
    """
    text: str

    def __eq__(self, other: object) -> bool:
        if isinstance(other, KeyText):
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


class ButtonText(Enum):
    # Кнопки, используемые в разных меню
    BIND_WITH_TG_USER = KeyText(text="🔗 Связать с пользователем")
    BIND_TO_YOURSELF = KeyText(text="🙋‍♂️ Привязать к себе")

    UNBIND_FROM_TG_USER = KeyText(text="🚫 Отвязать от пользователя")
    UNBIND_FROM_YOURSELF = KeyText(text="🔓 Отвязать от себя")

    CANCEL = KeyText(text="❌ Отменить")
    TURN_BACK = KeyText(text="◀️ Назад")

    OWN = KeyText(text="👤 Свои")
    WIREGUARD_USER = KeyText(text="🛡 Пользователя Wireguard")
    TELEGRAM_USER = KeyText(text="📩 Пользователя Telegram")

    SELECT_TELEGRAM_USER = KeyText(text="📌 Выбрать пользователя")
    ENTER_TELEGRAM_ID = KeyText(text="🔢 Ввести TID")
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, KeyText):
            return self.value == other
        if isinstance(other, str):
            return self.value == other
        return NotImplemented

    def __str__(self) -> str:
        """str(ButtonText.CANCEL) возвращает текст кнопки, а не имя Enum."""
        return str(self.value)

    def __repr__(self) -> str:
        """Возвращает более информативное представление."""
        return f"{self.__class__.__name__}.{self.name}({repr(self.value)})"