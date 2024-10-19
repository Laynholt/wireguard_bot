import os
import sqlite3
import logging

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
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_table()

    def _create_table(self):
        """
        Создание таблицы пользователей, если она не существует.
        """
        try:
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS linked_users (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    telegram_id BIGINT NOT NULL,
                                    user_name TEXT NOT NULL UNIQUE)''')
            
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS telegram_users (
                        telegram_id BIGINT PRIMARY KEY)''')

            self.conn.commit()
            self._db_loaded = True
        except sqlite3.Error as e:
            logger.error(f'Ошибка создания таблицы пользователей: {e}')
            self._db_loaded = False

    @property
    def db_loaded(self) -> bool:
        """
        Свойство, указывающее, загружена ли база данных.

        Returns:
            bool: True, если база данных загружена, иначе False.
        """
        return self._db_loaded

    def telegram_id_exists(self, telegram_id: int) -> bool:
        """
        Проверяет, существует ли пользователь с указанным telegram_id.

        Args:
            telegram_id (int): Идентификатор Telegram пользователя.

        Returns:
            bool: True, если пользователь существует, иначе False.
        """
        try:
            self.cursor.execute('SELECT * FROM linked_users WHERE telegram_id = ?', (telegram_id,))
            return self.cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f'Ошибка проверки существования пользователя: {e}')
            return False

    def user_exists(self, user_name: str) -> bool:
        """
        Проверяет, существует ли пользователь с указанным именем.

        Args:
            user_name (str): Имя пользователя.

        Returns:
            bool: True, если пользователь существует, иначе False.
        """
        try:
            self.cursor.execute('SELECT * FROM linked_users WHERE user_name = ?', (user_name,))
            return self.cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f'Ошибка проверки существования пользователя: {e}')
            return False
    
    def user_with_telegram_id_exists(self, telegram_id: int, user_name: str) -> bool:
        """
        Проверяет, существует ли пользователь с указанными telegram_id и user_name.

        Args:
            telegram_id (int): Идентификатор Telegram пользователя.
            user_name (str): Имя пользователя.

        Returns:
            bool: True, если пользователь существует, иначе False.
        """
        try:
            self.cursor.execute('SELECT * FROM linked_users WHERE telegram_id = ? AND user_name = ?', (telegram_id, user_name))
            return self.cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f'Ошибка проверки существования пользователя: {e}')
            return False

    def add_user(self, telegram_id: int, user_name: str) -> bool:
        """
        Добавляет пользователя в базу данных.

        Args:
            telegram_id (int): Идентификатор Telegram пользователя.
            user_name (str): Имя пользователя.

        Returns:
            bool: True, если пользователь успешно добавлен, иначе False.
        """
        try:
            self.cursor.execute('INSERT INTO linked_users (telegram_id, user_name) VALUES (?, ?)', (telegram_id, user_name))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f'Ошибка добавления пользователя: {e}')
            return False
        
    def add_telegram_user(self, telegram_id: int) -> bool:
        """
        Добавляет Telegram ID в базу данных.

        Args:
            telegram_id (int): Идентификатор Telegram пользователя.
            
        Returns:
            bool: True, если пользователь успешно добавлен, иначе False.
        """
        try:
            # Вставляем нового пользователя, если его еще нет в таблице
            self.cursor.execute('''INSERT OR IGNORE INTO telegram_users (telegram_id) 
                                VALUES (?)''', (telegram_id,))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка при добавлении пользователя с telegram_id {telegram_id}: {e}')
            return False

    def check_database_health(self) -> bool:
        """
        Проверяет состояние базы данных.

        Returns:
            bool: True, если база данных работает корректно, иначе False.
        """
        try:
            self.cursor.execute('SELECT 1 FROM linked_users LIMIT 1')
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка проверки здоровья базы данных: {e}')
            return False

    def get_users_by_telegram_id(self, telegram_id: int):
        """
        Возвращает список пользователей по telegram_id.

        Args:
            telegram_id (int): Идентификатор Telegram пользователя.

        Returns:
            list: Список имен пользователей с указанным telegram_id.
        """
        try:
            self.cursor.execute('SELECT user_name FROM linked_users WHERE telegram_id = ?', (telegram_id,))
            return [user_name[0] for user_name in self.cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f'Ошибка получения данных для telegram_id {telegram_id}: {e}')
            return []
        
    def get_telegram_id_by_user(self, user_name: str):
        """
        Возвращает список telegram_id по имени пользователя.

        Args:
            user_name (str): Имя пользователя.

        Returns:
            list[int]: Список telegram_id для указанного имени пользователя.
        """
        try:
            self.cursor.execute('SELECT telegram_id FROM linked_users WHERE user_name = ?', (user_name,))
            return [telegram_id[0] for telegram_id in self.cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f'Ошибка получения данных для {user_name}: {e}')
            return []

    def delete_user(self, user_name: str) -> bool:
        """
        Удаляет пользователя по имени.

        Args:
            user_name (str): Имя пользователя для удаления.

        Returns:
            bool: True, если пользователь успешно удален, иначе False.
        """
        try:
            self.cursor.execute('DELETE FROM linked_users WHERE user_name = ?', (user_name,))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f'Ошибка удаления пользователя {user_name}: {e}')
            return False

    def delete_users_by_telegram_id(self, telegram_id: int) -> bool:
        """
        Удаляет пользователей по telegram_id.

        Args:
            telegram_id (int): Идентификатор Telegram пользователей для удаления.

        Returns:
            bool: True, если пользователи успешно удалены, иначе False.
        """
        try:
            self.cursor.execute('DELETE FROM linked_users WHERE telegram_id = ?', (telegram_id,))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f'Ошибка удаления пользователей с telegram_id {telegram_id}: {e}')
            return False
        
    def delete_telegram_user(self, telegram_id: int) -> bool:
        """
        Удаление пользователя из таблицы telegram_users.

        Args:
            telegram_id (int): ID пользователя в Telegram.

        Returns:
            bool: True, если пользователь успешно удалён, иначе False.
        """
        try:
            # Удаляем пользователя по его telegram_id
            self.cursor.execute('''DELETE FROM telegram_users WHERE telegram_id = ?''', (telegram_id,))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка при удалении пользователя с telegram_id {telegram_id}: {e}')
            return False

    def is_telegram_user_exists(self, telegram_id: int) -> bool:
        """
        Проверка существования пользователя в таблице telegram_users.
        
        Args:
            telegram_id (int): ID пользователя в Telegram.

        Returns:
            bool: True, если пользователь существует, иначе False.
        """
        try:
            # Выполняем запрос для проверки существования пользователя
            self.cursor.execute('''SELECT 1 FROM telegram_users WHERE telegram_id = ? LIMIT 1''', (telegram_id,))
            result = self.cursor.fetchone()
            return result is not None
        except sqlite3.Error as e:
            logger.error(f'Ошибка при проверке существования пользователя с telegram_id {telegram_id}: {e}')
            return False

    def get_all_linked_data(self) -> list:
        """
        Возвращает список всех привязанных пользователей с их Telegram Id из таблицы linked_users.
        
        Returns:
            list: Список всех привязанных пользователей с их Telegram Id.
        """
        try:
            # Выполняем запрос для получения всех telegram_id из таблицы
            self.cursor.execute('''SELECT telegram_id, user_name FROM linked_users''')
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f'Ошибка при получении списка пользователей: {e}')
            return []

    def get_all_telegram_users(self) -> list:
        """
        Возвращает список всех пользователей из таблицы telegram_users.
        
        Returns:
            list: Список всех telegram_id пользователей.
        """
        try:
            # Выполняем запрос для получения всех telegram_id из таблицы
            self.cursor.execute('''SELECT telegram_id FROM telegram_users''')
            users = self.cursor.fetchall()
            # Преобразуем результат в список только из telegram_id
            return [user[0] for user in users]
        except sqlite3.Error as e:
            logger.error(f'Ошибка при получении списка пользователей: {e}')
            return []

    def __del__(self):
        """
        Закрывает соединение с базой данных.
        """
        if self.conn:
            self.conn.close()



import aiosqlite

class AsyncUserDatabase:
    def __init__(self, db_path: str):
        """
        Инициализация объекта базы данных.

        Args:
            db_path (str): Путь к файлу базы данных SQLite.
        """
        self.db_path = db_path
        self._db_loaded = False

    async def connect(self):
        """
        Подключение к базе данных и создание таблицы, если она не существует.
        """
        if not os.path.exists(self.db_path):
            logger.info(f'Файл базы данных не найден. Создаем новый файл: {self.db_path}')

        self.db_conn = await aiosqlite.connect(self.db_path)
        await self._create_table()

    async def _create_table(self):
        """
        Создание таблицы пользователей, если она не существует.
        """
        try:
            await self.db_conn.execute('''CREATE TABLE IF NOT EXISTS linked_users (
                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                            telegram_id BIGINT NOT NULL,
                                            user_name TEXT NOT NULL UNIQUE)''')
            
            await self.db_conn.execute('''CREATE TABLE IF NOT EXISTS telegram_users (
                        telegram_id BIGINT PRIMARY KEY)''')
            
            await self.db_conn.commit()
            self._db_loaded = True
        except Exception as e:
            logger.error(f'Ошибка создания таблицы пользователей: {e}')
            self._db_loaded = False

    @property
    def db_loaded(self) -> bool:
        """
        Свойство, указывающее, загружена ли база данных.

        Returns:
            bool: True, если база данных загружена, иначе False.
        """
        return self._db_loaded

    async def telegram_id_exists(self, telegram_id: int) -> bool:
        """
        Проверяет, существует ли пользователь с указанным telegram_id.

        Args:
            telegram_id (int): Идентификатор Telegram пользователя.

        Returns:
            bool: True, если пользователь существует, иначе False.
        """
        try:
            async with self.db_conn.execute('SELECT * FROM linked_users WHERE telegram_id = ?', (telegram_id,)) as cursor:
                return await cursor.fetchone() is not None
        except Exception as e:
            logger.error(f'Ошибка проверки существования пользователя: {e}')
            return False

    async def user_exists(self, user_name: str) -> bool:
        """
        Проверяет, существует ли пользователь с указанным именем.

        Args:
            user_name (str): Имя пользователя.

        Returns:
            bool: True, если пользователь существует, иначе False.
        """
        try:
            async with self.db_conn.execute('SELECT * FROM linked_users WHERE user_name = ?', (user_name,)) as cursor:
                return await cursor.fetchone() is not None
        except Exception as e:
            logger.error(f'Ошибка проверки существования пользователя: {e}')
            return False

    async def user_with_telegram_id_exists(self, telegram_id: int, user_name: str) -> bool:
        """
        Проверяет, существует ли пользователь с указанными telegram_id и user_name.

        Args:
            telegram_id (int): Идентификатор Telegram пользователя.
            user_name (str): Имя пользователя.

        Returns:
            bool: True, если пользователь существует, иначе False.
        """
        try:
            async with self.db_conn.execute('SELECT * FROM linked_users WHERE telegram_id = ? AND user_name = ?', (telegram_id, user_name)) as cursor:
                return await cursor.fetchone() is not None
        except Exception as e:
            logger.error(f'Ошибка проверки существования пользователя: {e}')
            return False

    async def add_user(self, telegram_id: int, user_name: str) -> bool:
        """
        Добавляет пользователя в базу данных.

        Args:
            telegram_id (int): Идентификатор Telegram пользователя.
            user_name (str): Имя пользователя.

        Returns:
            bool: True, если пользователь успешно добавлен, иначе False.
        """
        try:
            await self.db_conn.execute('INSERT INTO linked_users (telegram_id, user_name) VALUES (?, ?)', (telegram_id, user_name))
            await self.db_conn.commit()
            return True
        except Exception as e:
            await self.db_conn.rollback()
            logger.error(f'Ошибка добавления пользователя: {e}')
            return False

    async def check_database_health(self) -> bool:
        """
        Проверяет состояние базы данных.

        Returns:
            bool: True, если база данных работает корректно, иначе False.
        """
        try:
            async with self.db_conn.execute('SELECT 1 FROM linked_users LIMIT 1') as cursor:
                await cursor.fetchone()
            return True
        except Exception as e:
            logger.error(f'Ошибка проверки здоровья базы данных: {e}')
            return False

    async def get_users_by_telegram_id(self, telegram_id: int):
        """
        Возвращает список пользователей по telegram_id.

        Args:
            telegram_id (int): Идентификатор Telegram пользователя.

        Returns:
            list: Список имен пользователей с указанным telegram_id.
        """
        try:
            async with self.db_conn.execute('SELECT user_name FROM linked_users WHERE telegram_id = ?', (telegram_id,)) as cursor:
                return [user_name[0] for user_name in await cursor.fetchall()]
        except Exception as e:
            logger.error(f'Ошибка получения данных для telegram_id {telegram_id}: {e}')
            return []

    async def get_telegram_id_by_user(self, user_name: str):
        """
        Возвращает список telegram_id по имени пользователя.

        Args:
            user_name (str): Имя пользователя.

        Returns:
            list: Список telegram_id для указанного имени пользователя.
        """
        try:
            async with self.db_conn.execute('SELECT telegram_id FROM linked_users WHERE user_name = ?', (user_name,)) as cursor:
                return [telegram_id[0] for telegram_id in await cursor.fetchall()]
        except Exception as e:
            logger.error(f'Ошибка получения данных для {user_name}: {e}')
            return []

    async def delete_user(self, user_name: str) -> bool:
        """
        Удаляет пользователя по имени.

        Args:
            user_name (str): Имя пользователя для удаления.

        Returns:
            bool: True, если пользователь успешно удален, иначе False.
        """
        try:
            await self.db_conn.execute('DELETE FROM linked_users WHERE user_name = ?', (user_name,))
            await self.db_conn.commit()
            return True
        except Exception as e:
            await self.db_conn.rollback()
            logger.error(f'Ошибка удаления пользователя {user_name}: {e}')
            return False

    async def delete_users_by_telegram_id(self, telegram_id: int) -> bool:
        """
        Удаляет пользователей по telegram_id.

        Args:
            telegram_id (int): Идентификатор Telegram пользователей для удаления.

        Returns:
            bool: True, если пользователи успешно удалены, иначе False.
        """
        try:
            await self.db_conn.execute('DELETE FROM linked_users WHERE telegram_id = ?', (telegram_id,))
            await self.db_conn.commit()
            return True
        except Exception as e:
            await self.db_conn.rollback()
            logger.error(f'Ошибка удаления пользователей с telegram_id {telegram_id}: {e}')
            return False

    async def close(self):
        """
        Закрывает соединение с базой данных.
        """
        if self.db_conn:
            await self.db_conn.close()
            logger.info("Соединение с базой данных закрыто.")

    async def add_telegram_user(self, telegram_id: int) -> bool:
        """
        Добавление пользователя в таблицу telegram_users.
        
        Args:
            telegram_id (int): ID пользователя в Telegram.

        Returns:
            bool: True, если пользователь успешно добавлен, иначе False.
        """
        try:
            # Вставляем нового пользователя, если его еще нет в таблице
            await self.db_conn.execute('''INSERT OR IGNORE INTO telegram_users (telegram_id) 
                                VALUES (?)''', (telegram_id,))
            await self.db_conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка при добавлении пользователя с telegram_id {telegram_id}: {e}')
            return False

    async def delete_telegram_user(self, telegram_id: int) -> bool:
        """
        Удаление пользователя из таблицы telegram_users.

        Args:
            telegram_id (int): ID пользователя в Telegram.

        Returns:
            bool: True, если пользователь успешно удалён, иначе False.
        """
        try:
            # Удаляем пользователя по его telegram_id
            await self.db_conn.execute('''DELETE FROM telegram_users WHERE telegram_id = ?''', (telegram_id,))
            await self.db_conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f'Ошибка при удалении пользователя с telegram_id {telegram_id}: {e}')
            return False

    async def is_telegram_user_exists(self, telegram_id: int) -> bool:
        """
        Проверка существования пользователя в таблице telegram_users.
        
        Args:
            telegram_id (int): ID пользователя в Telegram.

        Returns:
            bool: True, если пользователь существует, иначе False.
        """
        try:
            # Выполняем запрос для проверки существования пользователя
            async with self.db_conn.execute('''SELECT 1 FROM telegram_users WHERE telegram_id = ? LIMIT 1''', (telegram_id,)) as cursor:
                result = await cursor.fetchone()
                return result is not None
        except sqlite3.Error as e:
            logger.error(f'Ошибка при проверке существования пользователя с telegram_id {telegram_id}: {e}')
            return False

    async def get_all_linked_data(self) -> list:
        """
        Возвращает список всех привязанных пользователей с их Telegram Id из таблицы linked_users.
        
        Returns:
            list: Список всех привязанных пользователей с их Telegram Id.
        """
        try:
            async with self.db_conn.execute('''SELECT telegram_id, user_name FROM linked_users''') as cursor:
                return list(await cursor.fetchall())
        except sqlite3.Error as e:
            logger.error(f'Ошибка при получении списка пользователей: {e}')
            return []

    async def get_all_telegram_users(self) -> list:
        """
        Возвращает список всех пользователей из таблицы telegram_users.
        
        Returns:
            list: Список всех telegram_id пользователей.
        """
        try:
            # Выполняем запрос для получения всех telegram_id из таблицы
            async with self.db_conn.execute('''SELECT telegram_id FROM telegram_users''') as cursor:
                return [telegram_id[0] for telegram_id in await cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f'Ошибка при получении списка пользователей: {e}')
            return []
