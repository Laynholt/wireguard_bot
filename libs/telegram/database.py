import os
import sqlite3
import logging
import threading
from contextlib import contextmanager
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
        self._db_path = db_path
        self._lock = threading.RLock()

        if not os.path.exists(db_path):
            logger.info(f'Файл базы данных не найден. Создаем новый файл: {db_path}')

        self._create_table()

    @contextmanager
    def _conn(self):
        """
        Открывает новое соединение на одну операцию.
        """
        with self._lock:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _create_table(self):
        """
        Создание таблиц пользователей, если они не существуют.
        """
        try:
            with self._conn() as conn:
                conn.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS linked_users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id BIGINT NOT NULL,
                        user_name TEXT NOT NULL UNIQUE
                    )
                    '''
                )

                conn.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS telegram_users (
                        telegram_id BIGINT PRIMARY KEY,
                        is_user_banned BOOLEAN NOT NULL DEFAULT 0
                    )
                    '''
                )
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
        """
        try:
            with self._conn() as conn:
                result = conn.execute(
                    '''SELECT 1 FROM linked_users WHERE telegram_id = ? LIMIT 1''',
                    (telegram_id,)
                ).fetchone()
            return result is not None
        except sqlite3.Error as e:
            logger.error(
                f'Ошибка при проверке существования пользователя Telegram c Id {telegram_id}: {e}'
            )
            return False

    def is_user_exists(self, user_name: WireguardUserName) -> bool:
        """
        Проверяет, существует ли пользователь Wireguard с указанным именем.
        """
        try:
            with self._conn() as conn:
                result = conn.execute(
                    'SELECT 1 FROM linked_users WHERE user_name = ? LIMIT 1',
                    (user_name,)
                ).fetchone()
            return result is not None
        except sqlite3.Error as e:
            logger.error(
                f'Ошибка при проверке существования пользователя Wireguard {user_name}: {e}'
            )
            return False

    def user_with_telegram_id_exists(self, telegram_id: TelegramId, user_name: WireguardUserName) -> bool:
        """
        Проверяет, существует ли пользователь Wireguard с указанным Telegram Id.
        """
        try:
            with self._conn() as conn:
                result = conn.execute(
                    'SELECT 1 FROM linked_users WHERE telegram_id = ? AND user_name = ? LIMIT 1',
                    (telegram_id, user_name)
                ).fetchone()
            return result is not None
        except sqlite3.Error as e:
            logger.error((
                'Ошибка при проверке существования пользователя Wireguard'
                f' {user_name} и Telegram Id {telegram_id}: {e}'
            ))
            return False

    def add_user(self, telegram_id: TelegramId, user_name: WireguardUserName) -> bool:
        """
        Добавляет пользователя Wireguard в базу данных.
        """
        try:
            with self._conn() as conn:
                conn.execute(
                    'INSERT INTO linked_users (telegram_id, user_name) VALUES (?, ?)',
                    (telegram_id, user_name)
                )
            return True
        except sqlite3.Error as e:
            logger.error(
                f'Ошибка добавления пользователя Wireguard {user_name} и Telegram Id {telegram_id}: {e}'
            )
            return False

    def add_telegram_user(self, telegram_id: TelegramId) -> bool:
        """
        Добавляет Telegram Id в базу данных telegram_users.
        """
        try:
            with self._conn() as conn:
                conn.execute(
                    '''INSERT OR IGNORE INTO telegram_users (telegram_id) VALUES (?)''',
                    (telegram_id,)
                )
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка при добавлении пользователя Telegram с Id {telegram_id}: {e}')
            return False

    def check_database_health(self) -> bool:
        """
        Проверяет состояние базы данных.
        """
        try:
            with self._conn() as conn:
                conn.execute('SELECT 1 FROM linked_users LIMIT 1').fetchone()
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка проверки здоровья базы данных: {e}')
            return False

    def get_users_by_telegram_id(self, telegram_id: TelegramId) -> List[WireguardUserName]:
        """
        Возвращает список пользователей Wireguard по Telegram Id.
        """
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    'SELECT user_name FROM linked_users WHERE telegram_id = ?',
                    (telegram_id,)
                ).fetchall()
            return [row[0] for row in rows]
        except sqlite3.Error as e:
            logger.error(f'Ошибка получения данных для telegram_id {telegram_id}: {e}')
            return []

    def get_telegram_id_by_user(self, user_name: WireguardUserName) -> List[TelegramId]:
        """
        Возвращает список Telegram Id, к которым привязан пользователь Wireguard.
        """
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    'SELECT telegram_id FROM linked_users WHERE user_name = ?',
                    (user_name,)
                ).fetchall()
            return [row[0] for row in rows]
        except sqlite3.Error as e:
            logger.error(f'Ошибка получения данных для пользователь Wireguard {user_name}: {e}')
            return []

    def delete_user(self, user_name: WireguardUserName) -> bool:
        """
        Удаляет пользователя Wireguard по имени.
        """
        try:
            with self._conn() as conn:
                conn.execute('DELETE FROM linked_users WHERE user_name = ?', (user_name,))
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка удаления пользователя Wireguard {user_name}: {e}')
            return False

    def delete_users_by_telegram_id(self, telegram_id: TelegramId) -> bool:
        """
        Удаляет пользователей Wireguard, привязанных к Telegram Id.
        """
        try:
            with self._conn() as conn:
                conn.execute('DELETE FROM linked_users WHERE telegram_id = ?', (telegram_id,))
            return True
        except sqlite3.Error as e:
            logger.error(
                f'Ошибка удаления пользователей Wireguard, привязанных к Telegram Id {telegram_id}: {e}'
            )
            return False

    def delete_telegram_user(self, telegram_id: TelegramId) -> bool:
        """
        Удаление пользователя Telegram из таблицы telegram_users.
        """
        try:
            with self._conn() as conn:
                conn.execute(
                    '''DELETE FROM telegram_users WHERE telegram_id = ?''',
                    (telegram_id,)
                )
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка при удалении пользователя Telegram с Id {telegram_id}: {e}')
            return False

    def is_telegram_user_exists(self, telegram_id: TelegramId) -> bool:
        """
        Проверка существования пользователя Telegram в таблице telegram_users.
        """
        try:
            with self._conn() as conn:
                result = conn.execute(
                    '''SELECT 1 FROM telegram_users WHERE telegram_id = ? LIMIT 1''',
                    (telegram_id,)
                ).fetchone()
            return result is not None
        except sqlite3.Error as e:
            logger.error(
                f'Ошибка при проверке существования пользователя Telegram с Id {telegram_id}: {e}'
            )
            return False

    def ban_telegram_user(self, telegram_id: TelegramId) -> bool:
        """
        Банит пользователя Telegram, устанавливая is_user_banned в True.
        """
        try:
            if not self.is_telegram_user_exists(telegram_id):
                return False
            with self._conn() as conn:
                conn.execute(
                    '''UPDATE telegram_users SET is_user_banned = 1 WHERE telegram_id = ?''',
                    (telegram_id,)
                )
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка при бане пользователя Telegram с Id {telegram_id}: {e}')
            return False

    def unban_telegram_user(self, telegram_id: TelegramId) -> bool:
        """
        Снимает бан с пользователя Telegram, устанавливая is_user_banned в False.
        """
        try:
            if not self.is_telegram_user_exists(telegram_id):
                return False
            with self._conn() as conn:
                conn.execute(
                    '''UPDATE telegram_users SET is_user_banned = 0 WHERE telegram_id = ?''',
                    (telegram_id,)
                )
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка при разбане пользователя Telegram с Id {telegram_id}: {e}')
            return False

    def get_all_linked_data(self) -> List[Tuple[TelegramId, WireguardUserName]]:
        """
        Возвращает список всех привязанных пользователей Wireguard
        с их Telegram Id из таблицы linked_users.
        """
        try:
            with self._conn() as conn:
                rows = conn.execute('''SELECT telegram_id, user_name FROM linked_users''').fetchall()
            return rows
        except sqlite3.Error as e:
            logger.error(f'Ошибка при получении списка пользователей Wireguard: {e}')
            return []

    def get_all_telegram_users(self) -> List[Tuple[TelegramId, TelegramBanStatus]]:
        """
        Возвращает список всех пользователей Telegram из таблицы telegram_users.
        """
        try:
            with self._conn() as conn:
                rows = conn.execute('''SELECT telegram_id, is_user_banned FROM telegram_users''').fetchall()
            return rows
        except sqlite3.Error as e:
            logger.error(f'Ошибка при получении списка пользователей Telegram: {e}')
            return []

    def __del__(self):
        """
        Соединения открываются на каждую операцию, закрывать нечего.
        """
        return
