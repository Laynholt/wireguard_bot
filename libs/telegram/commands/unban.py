from .base import *
from libs.telegram import messages

from telegram import (
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup
)


class UnbanTelegramUserCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId],
        telegram_user_ids_cache: set[TelegramId]
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids,
        )
    
        self.command_name = BotCommand.UNBAN_TELEGRAM_USER
        self.keyboard = ((
                KeyboardButton(
                    text=keyboards.BUTTON_SELECT_TELEGRAM_USER.text,
                    request_users=KeyboardButtonRequestUsers(
                        request_id=0,
                        user_is_bot=False,
                        request_username=True,
                    )
                ),
                keyboards.BUTTON_ENTER_TELEGRAM_ID.text
            ), (
                keyboards.BUTTON_CLOSE.text,
            )
        )
        self.telegram_user_ids_cache = telegram_user_ids_cache
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /unban_telegram_user: разблокирует пользователя Telegram 
        и раскомментирует его файлы конфигурации Wireguard.
        """
        if update.message is not None:
            await update.message.reply_text(
                messages.SELECT_TELEGRAM_USER,
                reply_markup=ReplyKeyboardMarkup(self.keyboard, one_time_keyboard=True),
            )
        if context.user_data is not None:
            context.user_data["command"] = self.command_name


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Разблокирует пользователя(-ей) телеграм и раскомментирует их Wireguard конфиги.
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
                if await self.__unban_user(update, context, entry):
                    need_restart_wireguard = True
                    
        else:
            if update.message.users_shared is None:
                await self._end_command(update, context)
                return
            
            for shared_user in update.message.users_shared.users:
                if await self.__unban_user(update, context, shared_user.user_id):
                    need_restart_wireguard = True

        await self._end_command(update, context)
        return need_restart_wireguard


    async def __unban_user(
        self,
        update: Update,
        context: CallbackContext,
        telegram_id: Union[TelegramId, str]
    ) -> Optional[bool]:
        """
        Разбанит передаваемого пользователя.
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
                         f'разблокировать администратора {telegram_username} ({tid}).'
            )
            await update.message.reply_text(f'Данную команду нельзя применять на администраторов!')
            return
        
        if not self.database.unban_telegram_user(tid):
            logger.error(f'Не удалось разблокировать пользователя {telegram_username} ({tid}).')
            await update.message.reply_text(
                f'Не удалось разблокировать пользователя {telegram_username} (<code>{tid}</code>).',
                parse_mode='HTML'
            )
            return
        
        user_configs = self.database.get_users_by_telegram_id(tid)
        
        need_restart_wireguard = False
        for user in user_configs:
            if wireguard.is_username_commented(user):
                ret_val = wireguard.comment_or_uncomment_user(user)
                
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

        self.telegram_user_ids_cache.add(tid)
        
        
        await update.message.reply_text(
            f'Пользователь {telegram_username} (<code>{tid}</code>) успешно разблокирован.',
            parse_mode='HTML'
        )

        return need_restart_wireguard


    async def _buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        if await self._close_button_handler(update, context):
            await self._end_command(update, context)
            return True
        
        if update.message is not None and update.message.text == keyboards.BUTTON_ENTER_TELEGRAM_ID:
            if update.effective_user is not None:
                await self._delete_message(update, context)
                await update.message.reply_text(messages.ENTER_TELEGRAM_IDS_MESSAGE)
            return True
        
        return False