from .base import *

from telegram import (
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup
)


class GetWireguardUsersByTIdCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId]
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids,
        )
    
        self.command_name = BotCommands.GET_USERS_BY_ID
        self.keyboard = ((
                KeyboardButton(
                    text=keyboards.BUTTON_TELEGRAM_USER.text,
                    request_users=KeyboardButtonRequestUsers(
                        request_id=0,
                        user_is_bot=False,
                        request_username=True,
                    )
                ),
                keyboards.BUTTON_OWN.text
            ), (
                keyboards.BUTTON_CLOSE.text,
            )
        )
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /get_users_by_id: показать, какие конфиги Wireguard привязаны к Telegram ID.
        """
        if update.message is not None:
            await update.message.reply_text(
                (
                    "Пожалуйста, выберите пользователя Telegram, привязки которого хотите увидеть.\n\n"
                    "Для отмены действия нажмите кнопку Закрыть."
                ),
                reply_markup=ReplyKeyboardMarkup(self.keyboard, one_time_keyboard=True),
            )
        if context.user_data is not None:
            context.user_data["command"] = self.command_name


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Возвращает список пользователей Wireguard, привязанных к данному Telegram.
        """
        try:
            if await self._buttons_handler(update, context):
                return
            
            if context.user_data is None or update.message is None:
                return
        
            if update.message.users_shared is None:
                return
            
            for shared_user in update.message.users_shared.users:
                await self.__get_bound_users_by_tid(
                    update, context, shared_user.user_id
                )
        
        finally:
            await self._end_command(update, context)


    async def __get_bound_users_by_tid(
        self,
        update: Update,
        context: CallbackContext,
        telegram_id: TelegramId
    ) -> None:
        """
        Показывает, какие user_name привязаны к Telegram ID (tid).
        """
        if not await self._validate_telegram_id(update, telegram_id):
            return

        if not await self._check_database_state(update):
            return

        telegram_username = await telegram_utils.get_username_by_id(telegram_id, context)

        if self.database.is_telegram_user_linked(telegram_id):
            user_names = self.database.get_users_by_telegram_id(telegram_id)
            if update.message is not None:
                await update.message.reply_text((
                        f"Пользователи Wireguard, прикрепленные к [{telegram_username}"
                        f" (<code>{telegram_id}</code>)]: "
                        f"[{', '.join([f'<code>{u}</code>' for u in sorted(user_names)])}]."
                    ),
                    parse_mode="HTML"
                )
        else:
            logger.info(
                    f"Ни один из пользователей Wireguard не прикреплен "
                    f"к [{telegram_username} ({telegram_id})] в базе данных."
                )
            if update.message is not None:
                await update.message.reply_text(
                    f"Ни один из пользователей Wireguard не прикреплен "
                    f"к [{telegram_username} (<code>{telegram_id}</code>)] в базе данных.",
                    parse_mode="HTML"
                )


    async def _buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        if await self._close_button_handler(update, context):
            return True
        
        if update.message is not None and update.message.text == keyboards.BUTTON_OWN:
            if update.effective_user is not None:
                await self._delete_message(update, context)
                await self.__get_bound_users_by_tid(
                    update, context, update.effective_user.id
                )
            return True
        
        return False