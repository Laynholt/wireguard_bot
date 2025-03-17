from typing import List, Optional, Union
from dataclasses import dataclass, field
from telegram import ReplyKeyboardMarkup


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