from typing import List, Optional, Union
from dataclasses import dataclass, field
from telegram import ReplyKeyboardMarkup

from libs.telegram.commands import BotCommand
from libs.telegram.keyboards import keys


KeyboardId = int

@dataclass
class Keyboard:
    _counter: int = field(init=False, repr=False, default=0)
    
    id: KeyboardId = field(init=False)
    title: str = ''
    reply_keyboard: Optional[ReplyKeyboardMarkup] = None
    parent: Optional["Keyboard"] = None
    children: List["Keyboard"] = field(default_factory=list)
    is_menu: bool = False
    
    def __post_init__(self) -> None:
        self.id = Keyboard._counter
        Keyboard._counter += 1
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Keyboard):
            return NotImplemented
        return self.id == other.id
    
    def __contains__(self, item: Union["Keyboard", KeyboardId, str]) -> bool:
        if isinstance(item, Keyboard):
            return item in self.children
        elif isinstance(item, KeyboardId):
            return any(child.id == item for child in self.children)
        elif isinstance(item, str):
            return any(child.title == item for child in self.children)
        return False

    def __repr__(self) -> str:
        return (f"{self.__class__.__name__}(id={self.id}, title={self.title!r}, "
                f"reply_keyboard={self.reply_keyboard!r}, "
                f"parent_id={self.parent.id if self.parent else None}, "
                f"children_ids={[child.id for child in self.children]})")
    
    def __str__(self) -> str:
        children_titles = ', '.join(child.title for child in self.children)
        return f"Keyboard <{self.title}> (id: {self.id}), children: [{children_titles}]"
    

    def get_child_by_id(self, child_id: KeyboardId) -> Optional["Keyboard"]:
        """
        Находит ребенка по его id.

        Args:
            child_id (int): ID клавиатуры.

        Returns:
            Optional[Keyboard]: Найденный объект или None.
        """
        return next((child for child in self.children if child.id == child_id), None)

    
    def get_descendant_by_id(self, child_id: KeyboardId) -> Optional["Keyboard"]:
        """
        Находит потомка (в любом поколении) по его id с использованием итеративного обхода.

        Args:
            child_id (KeyboardId): ID клавиатуры.

        Returns:
            Optional[Keyboard]: Найденный объект или None, если потомок с таким id отсутствует.
        """
        stack = list(self.children)  # Начинаем с прямых детей
        while stack:
            child = stack.pop()  # Извлекаем последний элемент (DFS)
            if child.id == child_id:
                return child
            # Добавляем потомков текущего ребенка в стек
            stack.extend(child.children)
        return None

    
    def add_parent(self, new_parent: "Keyboard") -> None:
        """
        Присваивает нового родителя, обновляя связи.

        - Если уже есть родитель, то старая связь удаляется.
        - Добавляется новая двусторонняя связь.

        Args:
            new_parent (Keyboard): Новый родитель.
        """
        if self.parent is not None:
            if self.parent == new_parent:
                return            
            self.parent.children.remove(self)  # Удаляем из старого родителя

        self.parent = new_parent  # Назначаем нового родителя
        if self not in new_parent.children:
            new_parent.children.append(self)  # Добавляем в список детей нового родителя


    def add_child(self, child: "Keyboard") -> None:
        """
        Добавляет ребенка к текущей клавиатуре, обновляя связи.

        - Если ребенок уже был привязан к другому родителю, то он отвязывается.
        - Создается новая двусторонняя связь.

        Args:
            child (Keyboard): Ребенок для добавления.
        """
        if child.parent is not None:
            if self == child.parent:
                return
            child.parent.children.remove(child)  # Удаляем из старого родителя

        child.parent = self  # Устанавливаем нового родителя
        if child not in self.children:
            self.children.append(child)  # Добавляем в список детей


# Подменю "Действия с пользователями WireGuard"
WIREGUARD_ACTIONS_KEYBOARD = Keyboard(
    title="⚙️ Действия с пользователями WireGuard",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.ADD_USER.pretty_text,),
            (BotCommand.REMOVE_USER.pretty_text,),
            (BotCommand.COM_UNCOM_USER.pretty_text,),
            (BotCommand.SHOW_USERS_STATE.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)

# Подменю "Привязка пользователей WireGuard"
WIREGUARD_BINDINGS_KEYBOARD = Keyboard(
    title="🔗 Привязка пользователей WireGuard",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.BIND_USER.pretty_text,),
            (BotCommand.UNBIND_USER.pretty_text,),
            (BotCommand.UNBIND_TELEGRAM_ID.pretty_text,),
            (BotCommand.GET_USERS_BY_ID.pretty_text,),
            (BotCommand.SHOW_ALL_BINDINGS.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)

# Подменю "Действия с пользователями Telegram"
TELEGRAM_ACTIONS_KEYBOARD = Keyboard(
    title="👤 Действия с пользователями Telegram",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.BAN_TELEGRAM_USER.pretty_text,),
            (BotCommand.UNBAN_TELEGRAM_USER.pretty_text,),
            (BotCommand.REMOVE_TELEGRAM_USER.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)

# Подменю "Конфигурационные файлы WireGuard"
WIREGUARD_CONFIG_KEYBOARD = Keyboard(
    title="📁 Конфигурационные файлы WireGuard",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.GET_CONFIG.pretty_text,),
            (BotCommand.GET_QRCODE.pretty_text,),
            (BotCommand.SEND_CONFIG.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)

# Подменю "Статистика WireGuard"
WIREGUARD_STATS_KEYBOARD = Keyboard(
    title="📊 Статистика WireGuard",
    reply_keyboard=ReplyKeyboardMarkup(
    (        
            (BotCommand.GET_MY_STATS.pretty_text,),
            (BotCommand.GET_USER_STATS.pretty_text,),
            (BotCommand.GET_ALL_STATS.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)
    
# Подменю "Информация о пользователях Telegram"
TELEGRAM_INFO_KEYBOARD = Keyboard(
    title="👥 Информация о пользователях Telegram",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.GET_TELEGRAM_ID.pretty_text,),
            (BotCommand.GET_TELEGRAM_USERS.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)

# Подменю "Основные команды"
GENERAL_COMMANDS_KEYBOARD = Keyboard(
    title="🛠 Основные команды",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.HELP.pretty_text,),
            (BotCommand.SEND_MESSAGE.pretty_text,),
            (BotCommand.RELOAD_WG_SERVER.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)


# Подменю "Конфигурационные файлы WireGuard" для пользователей
USER_WIREGUARD_CONFIG_KEYBOARD = Keyboard(
    title="📁 Конфигурационные файлы WireGuard",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.GET_CONFIG.pretty_text,),
            (BotCommand.GET_QRCODE.pretty_text,),
            (BotCommand.REQUEST_NEW_CONFIG.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)

# Подменю "Основные команды"
USER_GENERAL_COMMANDS_KEYBOARD = Keyboard(
    title="ℹ️ Основные команды",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.GET_TELEGRAM_ID.pretty_text,),
            (BotCommand.GET_MY_STATS.pretty_text,),
            (BotCommand.HELP.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)