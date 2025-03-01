import inspect
import logging

from abc import ABC, abstractmethod
from typing import Any, Iterable, List, Optional, Tuple, Union

from telegram import Update
from telegram.ext import CallbackContext
from telegram.error import TelegramError

from libs.telegram import keyboards
from libs.telegram.commands import BotCommands
from libs.telegram.types import TelegramId, WireguardUserName
from libs.telegram.database import UserDatabase

import libs.telegram.utils as telegram_utils

import libs.wireguard.utils as wireguard_utils
import libs.wireguard.user_control as wireguard


logger = logging.getLogger(__name__)


class BaseCommand(ABC):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId],
    ) -> None:
        self.database = database
        self.telegram_admin_ids = telegram_admin_ids

        self.command_name: Optional[BotCommands] = None  
        self.keyboard: Tuple[Any, ...] = ()
    

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
        if context.user_data is not None: 
            context.user_data["command"] = None
            context.user_data["wireguard_users"] = []

        if update.message is not None and update.effective_user is not None:
            await update.message.reply_text(
                f"Команда завершена. Выбрать новую команду можно из меню (/{BotCommands.MENU}).",
                reply_markup=(
                    keyboards.ADMIN_MENU
                    if update.effective_user.id in self.telegram_admin_ids
                    else keyboards.USER_MENU
                )
            )


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
    ) -> Optional[wireguard_utils.FunctionResult]:
        """
        Добавляет существующие user_name в список пользователей Wireguard для дальнейшей обработки,
        если user_name существует и корректен.
        """
        if not await self._validate_username(update, user_name):
            return None

        check_result = wireguard.check_user_exists(user_name)
        if check_result.status:
            if context.user_data is not None:
                context.user_data["wireguard_users"].append(user_name)
            return None
        return check_result


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
            ret_val = await self._create_list_of_wireguard_users(
                update, context, user_name
            )
            
            if ret_val is not None and ret_val.status is False:
                logger.error(ret_val.description)

    
    async def _buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        """
        Общий обработчик кнопок.
        
        Returns:
            bool: Возвращает True, если сообщение пользователя являлось кнопкой и было обработано.
            В ином случает возвращает False - продолжаем выполнение команды. 
        """
        if not self.keyboard:
            return False
        raise NotImplementedError(f"Необходимо переопределить обработчик кнопок для [{self.keyboard}].")
        
        
    async def _close_button_handler(self, update: Update, context: CallbackContext) -> bool:
        """
        Обработка кнопки Закрыть (BUTTON_CLOSE).
        Возвращает True, если нужно прервать дальнейший парсинг handle_text.
        """
        if not context.user_data:
            return False
        
        if update.message is None or update.message.text != keyboards.BUTTON_CLOSE:
            return False
        
        current_command = context.user_data.get("command", None)

        if current_command == self.command_name:
            await self._delete_message(update, context)
            if update.message is not None:
                await update.message.reply_text("Действие отменено.")
            return True
        return False


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