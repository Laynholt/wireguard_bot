import os
import sqlite3
import logging
from typing import List, Tuple

from .types import *

logger = logging.getLogger(__name__)

class UserDatabase:
    def __init__(self, db_path: str):
        """
        Инициализация объекта базы данных.

        Args:
            db_path (str): Путь к файлу базы данных SQLite.
        """
        self._db_loaded = False
        if not os.path.exists(db_path):
            logger.info(f'Файл базы данных не найден. Создаем новый файл: {db_path}')
        
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._cursor = self._connection.cursor()
        self._create_table()

    def _create_table(self):
        """
        Создание таблиц пользователей, если она не существует.
        """
        try:
            self._cursor.execute('''
                CREATE TABLE IF NOT EXISTS linked_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id BIGINT NOT NULL,
                    user_name TEXT NOT NULL UNIQUE
                )
            ''')
            
            self._cursor.execute('''
                CREATE TABLE IF NOT EXISTS telegram_users (
                    telegram_id BIGINT PRIMARY KEY,
                    is_user_banned BOOLEAN NOT NULL DEFAULT 0
                )
            ''')

            self._connection.commit()
            self._db_loaded = True
        except sqlite3.Error as e:
            logger.error(f'Ошибка создания таблиц пользователей: {e}')
            self._db_loaded = False

    @property
    def db_loaded(self) -> bool:
        """
        Свойство, указывающее, загружена ли база данных.

        Returns:
            bool: True, если база данных загружена, иначе False.
        """
        return self._db_loaded

    def is_telegram_user_linked(self, telegram_id: TelegramId) -> bool:
        """
        Проверка существования пользователя Telegram в таблице linked_users.
        
        Args:
            telegram_id (TelegramId): Id пользователя в Telegram.

        Returns:
            bool: True, если пользователь Telegram существует, иначе False.
        """
        try:
            self._cursor.execute(
                '''SELECT 1 FROM linked_users WHERE telegram_id = ? LIMIT 1''',
                (telegram_id,)
            )
            result = self._cursor.fetchone()
            return result is not None
        except sqlite3.Error as e:
            logger.error(
                f'Ошибка при проверке существования пользователя Telegram c Id {telegram_id}: {e}'
            )
            return False

    def is_user_exists(self, user_name: WireguardUserName) -> bool:
        """
        Проверяет, существует ли пользователь Wireguard с указанным именем.

        Args:
            user_name (WireguardUserName): Имя пользователя Wireguard.

        Returns:
            bool: True, если пользователь Wireguard существует, иначе False.
        """
        try:
            self._cursor.execute(
                'SELECT * FROM linked_users WHERE user_name = ?',
                (user_name,)
            )
            return self._cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(
                f'Ошибка при проверке существования пользователя Wireguard {user_name}: {e}'
            )
            return False
    
    def user_with_telegram_id_exists(self, telegram_id: TelegramId, user_name: WireguardUserName) -> bool:
        """
        Проверяет, существует ли пользователь Wireguard с указанным Telegram Id.

        Args:
            telegram_id (TelegramId): Id пользователя Telegram.
            user_name (WireguardUserName): Имя пользователя Wireguard.

        Returns:
            bool: True, если пользователь Wireguard существует, иначе False.
        """
        try:
            self._cursor.execute(
                'SELECT * FROM linked_users WHERE telegram_id = ? AND user_name = ?',
                (telegram_id, user_name)
            )
            return self._cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error((
                'Ошибка при проверке существования пользователя Wireguard'
                f' {user_name} и Telegram Id {telegram_id}: {e}'
            ))
            return False

    def add_user(self, telegram_id: TelegramId, user_name: WireguardUserName) -> bool:
        """
        Добавляет пользователя Wireguard в базу данных.

        Args:
            telegram_id (TelegramId): Id пользователя Telegram.
            user_name (WireguardUserName): Имя пользователя Wireguard.

        Returns:
            bool: True, если пользователь Wireguard успешно добавлен, иначе False.
        """
        try:
            self._cursor.execute(
                'INSERT INTO linked_users (telegram_id, user_name) VALUES (?, ?)',
                (telegram_id, user_name)
            )
            self._connection.commit()
            return True
        except sqlite3.Error as e:
            self._connection.rollback()
            logger.error(
                f'Ошибка добавления пользователя Wireguard {user_name} и Telegram Id {telegram_id}: {e}'
            )
            return False
        
    def add_telegram_user(self, telegram_id: TelegramId) -> bool:
        """
        Добавляет Telegram Id в базу данных telegram_users.

        Args:
            telegram_id (TelegramId): Id пользователя Telegram.
            
        Returns:
            bool: True, если пользователь Telegram успешно добавлен, иначе False.
        """
        try:
            # Вставляем нового пользователя, если его еще нет в таблице
            self._cursor.execute(
                '''INSERT OR IGNORE INTO telegram_users (telegram_id) VALUES (?)''',
                (telegram_id,)
            )
            self._connection.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка при добавлении пользователя Telegram с Id {telegram_id}: {e}')
            return False

    def check_database_health(self) -> bool:
        """
        Проверяет состояние базы данных.

        Returns:
            bool: True, если база данных работает корректно, иначе False.
        """
        try:
            self._cursor.execute('SELECT 1 FROM linked_users LIMIT 1')
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка проверки здоровья базы данных: {e}')
            return False

    def get_users_by_telegram_id(self, telegram_id: TelegramId) -> List[WireguardUserName]:
        """
        Возвращает список пользователей Wireguard по Telegram Id, к которому они привязаны.

        Args:
            telegram_id (TelegramId): Id пользователя Telegram.

        Returns:
            List[WireguardUserName]: Список имен пользователей с указанным Telegram Id.
        """
        try:
            self._cursor.execute(
                'SELECT user_name FROM linked_users WHERE telegram_id = ?',
                (telegram_id,)
            )
            return [user_name[0] for user_name in self._cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f'Ошибка получения данных для telegram_id {telegram_id}: {e}')
            return []
        
    def get_telegram_id_by_user(self, user_name: WireguardUserName) -> List[TelegramId]:
        """
        Возвращает список Telegram Id, к которым привязан пользователь Wireguard.

        Args:
            user_name (WireguardUserName): Имя пользователя Wireguard.

        Returns:
            List[TelegramId]: Список Telegram Id для указанного пользователя Wireguard.
        """
        try:
            self._cursor.execute(
                'SELECT telegram_id FROM linked_users WHERE user_name = ?',
                (user_name,)
            )
            return [telegram_id[0] for telegram_id in self._cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f'Ошибка получения данных для пользователь Wireguard {user_name}: {e}')
            return []

    def delete_user(self, user_name: WireguardUserName) -> bool:
        """
        Удаляет пользователя Wireguard по имени.

        Args:
            user_name (WireguardUserName): Имя пользователя Wireguard для удаления.

        Returns:
            bool: True, если пользователь Wireguard успешно удален, иначе False.
        """
        try:
            self._cursor.execute('DELETE FROM linked_users WHERE user_name = ?', (user_name,))
            self._connection.commit()
            return True
        except sqlite3.Error as e:
            self._connection.rollback()
            logger.error(f'Ошибка удаления пользователя Wireguard {user_name}: {e}')
            return False

    def delete_users_by_telegram_id(self, telegram_id: TelegramId) -> bool:
        """
        Удаляет пользователей Wireguard, привязанных к Telegram Id.

        Args:
            telegram_id (TelegramId): Id пользователя в Telegram, к которому привязаны пользователи Wireguard.

        Returns:
            bool: True, если пользователи Wireguard успешно удалены, иначе False.
        """
        try:
            self._cursor.execute('DELETE FROM linked_users WHERE telegram_id = ?', (telegram_id,))
            self._connection.commit()
            return True
        except sqlite3.Error as e:
            self._connection.rollback()
            logger.error(
                f'Ошибка удаления пользователей Wireguard, привязанных к Telegram Id {telegram_id}: {e}'
            )
            return False
        
    def delete_telegram_user(self, telegram_id: TelegramId) -> bool:
        """
        Удаление пользователя Telegram из таблицы telegram_users.

        Args:
            telegram_id (TelegramId): Id пользователя в Telegram.

        Returns:
            bool: True, если пользователь Telegram успешно удалён, иначе False.
        """
        try:
            # Удаляем пользователя по его telegram_id
            self._cursor.execute(
                '''DELETE FROM telegram_users WHERE telegram_id = ?''',
                (telegram_id,)
            )
            self._connection.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка при удалении пользователя Telegram с Id {telegram_id}: {e}')
            return False

    def is_telegram_user_exists(self, telegram_id: TelegramId) -> bool:
        """
        Проверка существования пользователя Telegram в таблице telegram_users.
        
        Args:
            telegram_id (TelegramId): Id пользователя в Telegram.

        Returns:
            bool: True, если пользователь Telegram существует, иначе False.
        """
        try:
            # Выполняем запрос для проверки существования пользователя
            self._cursor.execute(
                '''SELECT 1 FROM telegram_users WHERE telegram_id = ? LIMIT 1''',
                (telegram_id,)
            )
            result = self._cursor.fetchone()
            return result is not None
        except sqlite3.Error as e:
            logger.error(
                f'Ошибка при проверке существования пользователя Telegram с Id {telegram_id}: {e}'
            )
            return False
    
    def ban_telegram_user(self, telegram_id: TelegramId) -> bool:
        """
        Банит пользователя Telegram, устанавливая is_user_banned в True.
        
        Args:
            telegram_id (TelegramId): Id пользователя в Telegram.
        
        Returns:
            bool: True, если операция выполнена успешно, иначе False.
        """
        try:
            if not self.is_telegram_user_exists(telegram_id):
                return False
            self._cursor.execute(
                '''UPDATE telegram_users SET is_user_banned = 1 WHERE telegram_id = ?''',
                (telegram_id,)
            )
            self._connection.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка при бане пользователя Telegram с Id {telegram_id}: {e}')
            return False

    def unban_telegram_user(self, telegram_id: TelegramId) -> bool:
        """
        Снимает бан с пользователя Telegram, устанавливая is_user_banned в False.
        
        Args:
            telegram_id (TelegramId): Id пользователя в Telegram.
        
        Returns:
            bool: True, если операция выполнена успешно, иначе False.
        """
        try:
            if not self.is_telegram_user_exists(telegram_id):
                return False
            self._cursor.execute(
                '''UPDATE telegram_users SET is_user_banned = 0 WHERE telegram_id = ?''',
                (telegram_id,)
            )
            self._connection.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка при разбане пользователя Telegram с Id {telegram_id}: {e}')
            return False

    def get_all_linked_data(self) -> List[Tuple[TelegramId, WireguardUserName]]:
        """
        Возвращает список всех привязанных пользователей Wireguard 
        с их Telegram Id из таблицы linked_users.
        
        Returns:
            List[Tuple[TelegramId, WireguardUserName]]: Список кортежей 
            (Telegram Id, пользователь Wireguard).
        """
        try:
            # Выполняем запрос для получения всех telegram_id из таблицы
            self._cursor.execute('''SELECT telegram_id, user_name FROM linked_users''')
            return self._cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f'Ошибка при получении списка пользователей Wireguard: {e}')
            return []

    def get_all_telegram_users(self) -> List[Tuple[TelegramId, TelegramBanStatus]]:
        """
        Возвращает список всех пользователей Telegram из таблицы telegram_users.
        
        Returns:
            List[Tuple[TelegramId, TelegramBanStatus]]: Список кортежей всех 
            Telegram Id пользователей и их статусов.
        """
        try:
            # Выполняем запрос для получения всех telegram_id из таблицы
            self._cursor.execute('''SELECT telegram_id, is_user_banned FROM telegram_users''')
            users = self._cursor.fetchall()
            # Преобразуем результат в список только из telegram_id
            return users
        except sqlite3.Error as e:
            logger.error(f'Ошибка при получении списка пользователей Telegram: {e}')
            return []

    def __del__(self):
        """
        Закрывает соединение с базой данных.
        """
        if self._connection:
            self._connection.close()