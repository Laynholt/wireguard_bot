import asyncio
import inspect
import logging

from enum import Enum
from abc import ABC, abstractmethod
from typing import Any, Iterable, List, Optional, Tuple, Union

from telegram import Update
from telegram.ext import CallbackContext
from telegram.error import TelegramError

from libs.telegram.keyboards.menu_keyboard import Keyboard
from libs.telegram import keyboards
from libs.telegram.commands import BotCommand
from libs.telegram.types import TelegramId, WireguardUserName
from libs.telegram.database import UserDatabase

import libs.telegram.utils as telegram_utils
import libs.wireguard.user_control as wireguard


logger = logging.getLogger(__name__)


class ContextDataKeys(str, Enum):
    COMMAND = 'command'
    WIREGUARD_USERS = 'wireguard_users'
    CURRENT_MENU = 'current_menu'
    STATS_EXPORT_PREFIX = 'stats_export_'


class BaseCommand(ABC):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        self.database = database

        self.command_name: Optional[BotCommand] = None
        self.keyboard: Optional[Keyboard] = None
    

    async def request_input(self, update: Update, context: CallbackContext) -> None:
        """Запрашивает ввод у пользователя (необязательно)."""
        raise NotImplementedError("Эта команда не требует ввода.")
    
    
    @abstractmethod
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Основной метод выполнения команды.

        Returns:
            Optional[bool]: Если возвращает True, в таком случае нужно перезагрузить Wireguard.
        """
        pass
    

    async def _check_database_state(self, update: Update) -> bool:
        """
        Проверяет, загружена ли база данных.
        Если база не загружена, оповещает пользователя и возвращает False.
        """
        if not self.database.db_loaded:
            logger.error("Ошибка! База данных не загружена!")
            if update.message is not None:
                await update.message.reply_text(
                    "⚙️ <b>Технические неполадки</b>\n\n"
                    "📞 Пожалуйста, свяжитесь с администратором.",
                    parse_mode="HTML"
                )
            return False
        return True


    async def _end_command(self, update: Update, context: CallbackContext) -> None:
        """
        Универсальная функция завершения команды. Очищает данные о команде
        и предлагает меню в зависимости от прав пользователя.
        """
        if context.user_data is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Context user_data is None в функции {curr_frame.f_code.co_name}')
            return
        
        keyboard = keyboards.KEYBOARD_MANAGER.get_keyboard(context.user_data[ContextDataKeys.CURRENT_MENU])
        if keyboard is None:
            logger.error(f'Не удалось найти клавиатуру с индексом {context.user_data[ContextDataKeys.CURRENT_MENU]}')
        
        else:
            if update.message is not None and update.effective_user is not None:
                await update.message.reply_text(
                    f"Команда завершена. Выбрать новую команду можно из меню (/{BotCommand.MENU}).",
                    reply_markup=keyboard.reply_keyboard
                )
        
        context.user_data[ContextDataKeys.COMMAND] = None
        context.user_data[ContextDataKeys.WIREGUARD_USERS] = []


    async def _validate_username(self, update: Update, user_name: WireguardUserName) -> bool:
        """
        Проверяет формат имени пользователя Wireguard (латинские буквы и цифры).
        """
        if not telegram_utils.validate_username(user_name):
            if update.message is not None:
                await update.message.reply_text(
                    f"Неверный формат для имени пользователя [{user_name}]. "
                    f"Имя пользователя может содержать только латинские буквы и цифры."
                )
            return False
        return True


    async def _validate_telegram_id(self, update: Update, telegram_id: Union[TelegramId, str]) -> bool:
        """
        Проверяет корректность Telegram ID (целое число).
        """
        if not telegram_utils.validate_telegram_id(telegram_id):
            if update.message is not None:
                await update.message.reply_text(
                    f"Неверный формат для Telegram ID [{telegram_id}]. "
                    f"Telegram ID должен быть целым числом."
                )
            return False
        return True
    
    
    async def _create_list_of_wireguard_users(
        self,
        update: Update,
        context: CallbackContext,
        user_name: str
    ) -> bool:
        """
        Добавляет существующие user_name в список пользователей Wireguard для дальнейшей обработки,
        если user_name существует и корректен.
        """
        if not await self._validate_username(update, user_name):
            return False

        check_result = await asyncio.to_thread(wireguard.check_user_exists, user_name)
        if check_result.status:
            if context.user_data is not None:
                context.user_data[ContextDataKeys.WIREGUARD_USERS].append(user_name)
            logger.info(check_result.description)
        else:
            logger.error(check_result.description)
        
        if update.message is not None:
            await update.message.reply_text(check_result.description)
                    
        return check_result.status


    async def _create_list_of_wireguard_users_by_telegram_id(
        self,
        update: Update,
        context: CallbackContext,
        telegram_id: TelegramId
    ) -> None:
        """
        Добавляет список конфигов пользователя Telegram в список пользователей 
        Wireguard для дальнейшей обработки, если user_name существует и корректен.
        """
        
        if not await self._check_database_state(update):
            return
        
        if update.message is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
            return
        
        if context.user_data is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Context user_data is None в функции {curr_frame.f_code.co_name}')
            return


        wireguard_users = self.database.get_users_by_telegram_id(telegram_id)
        for user_name in wireguard_users:
            await self._create_list_of_wireguard_users(
                update, context, user_name
            )
            
    
    async def _buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        """
        Общий обработчик кнопок.
        
        Returns:
            bool: Возвращает True, если сообщение пользователя являлось кнопкой и было обработано.
            В ином случает возвращает False - продолжаем выполнение команды. 
        """
        if self.keyboard is None:
            return False
        raise NotImplementedError(f"Необходимо переопределить обработчик кнопок для [{self.keyboard}].")
        
        
    async def _cancel_button_handler(self, update: Update, context: CallbackContext) -> bool:
        """
        Обработка кнопки отменить (ButtonText.CANCEL).
        Возвращает True, если нужно прервать дальнейший парсинг handle_text.
        """        
        if update.message is None or update.message.text != keyboards.ButtonText.CANCEL:
            return False
        
        await self._delete_message(update, context)
        await update.message.reply_text("Действие отменено.")
        return True


    async def _turn_back_button_handler(self, update: Update, context: CallbackContext) -> bool:
        """
        Обработка кнопки вернуться назад (ButtonText.TURN_BACK).
        Возвращает True, если нужно прервать дальнейший парсинг handle_text.
        """
        if context.user_data is None:
            return False
        
        if update.message is None or update.message.text != keyboards.ButtonText.TURN_BACK:
            return False
        
        await self._delete_message(update, context)
        
        keyboard = keyboards.KEYBOARD_MANAGER.get_keyboard(context.user_data[ContextDataKeys.CURRENT_MENU])
        if keyboard is None:
            logger.error(f'Не удалось найти клавиатуру с индексом {context.user_data[ContextDataKeys.CURRENT_MENU]}')
            return False
        
        prev_keyboard = keyboard.parent if keyboard.parent is not None else keyboard
        context.user_data[ContextDataKeys.CURRENT_MENU] = prev_keyboard.id
        await update.message.reply_text(
            f"Возврат в {prev_keyboard.title}.", reply_markup=prev_keyboard.reply_keyboard
        )
        return True


    async def _delete_message(self, update: Update, context: CallbackContext) -> None:
        """
        Удаляет последнее сообщение пользователя из чата (обычно нажатую кнопку).
        """
        if update.message is not None:
            try:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id, message_id=update.message.message_id
                )
            except TelegramError as e:
                logger.error(f"Не удалось удалить сообщение: {e}")
