from .base import *
from libs.telegram import messages

from telegram import (
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup
)


class RemoveTelegramUserCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId],
        telegram_user_ids_cache: set[TelegramId]
    ) -> None:
        super().__init__(
            database
        )
    
        self.command_name = BotCommand.REMOVE_TELEGRAM_USER
        self.keyboard = keyboards.Keyboard(
            title=BotCommand.REMOVE_TELEGRAM_USER.pretty_text,
            reply_keyboard=ReplyKeyboardMarkup(
                ((
                    KeyboardButton(
                        text=keyboards.ButtonText.SELECT_TELEGRAM_USER.value.text,
                        request_users=KeyboardButtonRequestUsers(
                            request_id=0,
                            user_is_bot=False,
                            request_username=True,
                        )
                    ),
                    keyboards.ButtonText.ENTER_TELEGRAM_ID.value.text
                    ), (
                        keyboards.ButtonText.CANCEL.value.text,
                    )
                ),
                one_time_keyboard=True
            )
        )
        self.keyboard.add_parent(keyboards.TELEGRAM_ACTIONS_KEYBOARD)
        
        self.telegram_admin_ids = telegram_admin_ids
        self.telegram_user_ids_cache = telegram_user_ids_cache
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /remove_telegram_user: удаляет пользователя Telegram 
        вместе с его файлами конфигурации Wireguard.
        """
        if self.keyboard is None:
            return
        
        if update.message is not None:
            await update.message.reply_text(
                messages.SELECT_TELEGRAM_USER,
                reply_markup=self.keyboard.reply_keyboard
            )
        if context.user_data is not None:
            context.user_data[ContextDataKeys.COMMAND] = self.command_name


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Удаляет пользователя(-ей) телеграм и его(их) Wireguard конфиги.
        """
        if await self._buttons_handler(update, context):
            return
        
        if context.user_data is None or update.message is None:
            await self._end_command(update, context)
            return
        
        need_restart_wireguard = False
        entries = update.message.text.split() if update.message.text is not None else []
        if entries:
            for entry in entries:
                if await self.__remove_user(update, context, entry):
                    need_restart_wireguard = True
                    
        else:
            if update.message.users_shared is None:
                await self._end_command(update, context)
                return
            
            for shared_user in update.message.users_shared.users:
                if await self.__remove_user(update, context, shared_user.user_id):
                    need_restart_wireguard = True

        await self._end_command(update, context)
        return need_restart_wireguard


    async def __remove_user(
        self,
        update: Update,
        context: CallbackContext,
        telegram_id: Union[TelegramId, str]
    ) -> Optional[bool]:
        """
        Удаляет передаваемого пользователя.
        """
        if not await self._check_database_state(update):
            return

        if update.message is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
            return

        if update.effective_user is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
            return

        if not await self._validate_telegram_id(update, telegram_id):
            return
        
        tid = int(telegram_id)
        telegram_username = await telegram_utils.get_username_by_id(tid, context)
        
        req_tid = update.effective_user.id
        req_telegram_username = await telegram_utils.get_username_by_id(req_tid, context)        
        
        if tid in self.telegram_admin_ids:
            logger.error(f'Пользователь {req_telegram_username} ({req_tid}) пытался '
                         f'удалить администратора {telegram_username} ({tid}).'
            )
            await update.message.reply_text(f'Данную команду нельзя применять на администраторов!')
            return
        
        user_configs = self.database.get_users_by_telegram_id(tid)
        
        need_restart_wireguard = False
        for user in user_configs:
            # Удаляем конфиг пользователя
            ret_val = wireguard.remove_user(user)
            
            if ret_val is not None:
                # Выводим сообщение с результатом (ошибка или успех)
                msg = f'Для {telegram_username} ({tid}): {ret_val.description}'
                pretty_msg = f'Для {telegram_username} (<code>{tid}</code>): {ret_val.description}'
                
                await update.message.reply_text(pretty_msg, parse_mode='HTML')
                if ret_val.status:
                    need_restart_wireguard = True
                    logger.info(msg)
                else:
                    logger.error(msg)


        # Отвязываем от него все конфиги
        if self.database.is_telegram_user_linked(tid):
            if self.database.delete_users_by_telegram_id(tid):
                logger.info(
                    f"Для {telegram_username} ({tid}): Пользователи Wireguard успешно отвязаны."
                )
                if update.message is not None:
                    await update.message.reply_text(
                        f"Для {telegram_username} (<code>{tid}</code>):"
                        " Пользователи Wireguard успешно отвязаны.",
                        parse_mode='HTML'
                    )
            else:
                logger.info(
                    f"Для {telegram_username} ({tid}): Не удалось отвязать пользователей Wireguard."
                )
                if update.message is not None:
                    await update.message.reply_text(
                        f"Для {telegram_username} (<code>{tid}</code>):"
                        f" Не удалось отвязать пользователей Wireguard.",
                        parse_mode='HTML'
                    )
        else:
            logger.info(
                    f"Для {telegram_username} ({tid}): Ни один из пользователей Wireguard не прикреплен."
                )
            if update.message is not None:
                await update.message.reply_text(
                    f"Для {telegram_username} (<code>{tid}</code>):"
                    " Ни один из пользователей Wireguard не прикреплен.",
                    parse_mode='HTML'
                )
        
        # Удаляем пользователя из бд
        if self.database.is_telegram_user_exists(tid):
            if self.database.delete_telegram_user(tid):
                logger.info(f"Для {telegram_username} ({tid}): Пользователь успешно удален из бд.")
                await update.message.reply_text(
                    f"Для {telegram_username} (<code>{tid}</code>): Пользователь успешно удален из бд.",
                    parse_mode='HTML'
                )
            else:
                logger.error(f"Для {telegram_username} ({tid}): Не удалось удалить пользователя из бд.")
                await update.message.reply_text(
                    f"Для {telegram_username} (<code>{tid}</code>): Не удалось удалить пользователя из бд.",
                    parse_mode='HTML'
                )
        
        # Удаляем его id из кэша
        if tid in self.telegram_user_ids_cache:
            self.telegram_user_ids_cache.remove(tid)

        return need_restart_wireguard


    async def _buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        if await self._cancel_button_handler(update, context):
            await self._end_command(update, context)
            return True
        
        if update.message is not None and update.message.text == keyboards.ButtonText.ENTER_TELEGRAM_ID:
            if update.effective_user is not None:
                await self._delete_message(update, context)
                await update.message.reply_text(messages.ENTER_TELEGRAM_IDS_MESSAGE)
            return True
        
        return False