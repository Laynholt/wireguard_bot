from encodings.punycode import T
from typing import Dict, Final
from .keys import *
from .keyboards import *


class KeyboardManager:
    def __init__(self) -> None:
        """Инициализация менеджера клавиатур."""
        self.__admin_keyboard: Keyboard = Keyboard(
            title='Главное меню Администратора',
            is_menu=True
        )
        self.__user_keyboard: Keyboard = Keyboard(
            title='Главное меню Пользователя',
            is_menu=True
        )
        self.__manager: Dict[KeyboardId, Keyboard] = {
            self.__admin_keyboard.id: self.__admin_keyboard,
            self.__user_keyboard.id: self.__user_keyboard
        }

    def __add_to_keyboard(self, keyboard: Keyboard, is_admin_keyboard: bool = False) -> None:
        kb = self.__admin_keyboard if is_admin_keyboard else self.__user_keyboard
        kb.add_child(keyboard)
        kb.reply_keyboard = ReplyKeyboardMarkup(
            tuple([
                (child.title,) for child in kb.children
            ]),
            resize_keyboard=True,
            one_time_keyboard=False,
        )
        
        self.__manager.update({keyboard.id: keyboard})

    def add_to_admin_keyboard(self, keyboard: Keyboard) -> None:
        """
        Добавляет клавиатуру в админское меню.
        """
        self.__add_to_keyboard(keyboard, is_admin_keyboard=True)
        
    def add_to_user_keyboard(self, keyboard: Keyboard) -> None:
        """
        Добавляет клавиатуру в пользовательском меню.
        """
        self.__add_to_keyboard(keyboard)

    def get_keyboard(self, index: KeyboardId) -> Optional[Keyboard]:
        """
        Возвращает объект Keyboard по индексу.

        Args:
            index (KeyboardIndex): Индекс в списке клавиатур.

        Returns:
            Optional[Keyboard]: Найденный объект Keyboard или None, если индекс некорректный.
        """
        if index in self.__manager:
            return self.__manager.get(index)
        
        keyboard = self.__admin_keyboard.get_descendant_by_id(index)
        if keyboard is not None:
            return keyboard
        
        return self.__user_keyboard.get_descendant_by_id(index)
        
    def get_admin_main_keyboard(self) -> Keyboard:
        return self.__admin_keyboard
    
    def get_user_main_keyboard(self) -> Keyboard:
        return self.__user_keyboard
    

KEYBOARD_MANAGER: Final = KeyboardManager()
KEYBOARD_MANAGER.add_to_admin_keyboard(WIREGUARD_ACTIONS_KEYBOARD)
KEYBOARD_MANAGER.add_to_admin_keyboard(WIREGUARD_BINDINGS_KEYBOARD)
KEYBOARD_MANAGER.add_to_admin_keyboard(WIREGUARD_CONFIG_KEYBOARD)
KEYBOARD_MANAGER.add_to_admin_keyboard(WIREGUARD_STATS_KEYBOARD)
KEYBOARD_MANAGER.add_to_admin_keyboard(TELEGRAM_ACTIONS_KEYBOARD)
KEYBOARD_MANAGER.add_to_admin_keyboard(TELEGRAM_INFO_KEYBOARD)
KEYBOARD_MANAGER.add_to_admin_keyboard(GENERAL_COMMANDS_KEYBOARD)

KEYBOARD_MANAGER.add_to_user_keyboard(USER_WIREGUARD_CONFIG_KEYBOARD)
KEYBOARD_MANAGER.add_to_user_keyboard(USER_GENERAL_COMMANDS_KEYBOARD)