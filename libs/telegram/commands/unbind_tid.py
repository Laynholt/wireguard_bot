from .base import *

from telegram import (
    KeyboardButton,
        ReplyKeyboardMarkup,
    KeyboardButtonRequestUsers
)


class UnbindTelegramUserCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId]
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids,
        )
    
        self.command_name = BotCommands.UNBIND_TELEGRAM_ID
        self.keyboard = ((
                KeyboardButton(
                    text=keyboards.BUTTON_UNBIND_FROM_TG_USER.text,
                    request_users=KeyboardButtonRequestUsers(
                        request_id=0,
                        user_is_bot=False,
                        request_username=True,
                    )
                ),
                keyboards.BUTTON_UNBIND_FROM_YOURSELF.text
            ), (
                keyboards.BUTTON_CLOSE.text,
            )
        )
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /unbind_telegram_id: отвязывает все конфиги Wireguard по конкретному Telegram ID.
        """
        if update.message is not None:
            await update.message.reply_text(
                (
                    "Пожалуйста, выберите пользователя Telegram, которого хотите отвязать.\n\n"
                    "Для отмены действия нажмите кнопку Закрыть."
                ),
                reply_markup=ReplyKeyboardMarkup(self.keyboard, one_time_keyboard=True),
            )
        if context.user_data is not None:
            context.user_data["command"] = self.command_name


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Отвязывает пользователя Telegram от всех его конфигов Wireguard.
        """
        try:
            if await self.__buttons_handler(update, context):
                return
            
            if context.user_data is None or update.message is None:
                return
        
            if update.message.users_shared is None:
                return
            
            for shared_user in update.message.users_shared.users:
                await self.__unbind_telegram_id(
                    update, context, shared_user.user_id
                )
        
        finally:
            await self.__end_command(update, context)


    async def __unbind_telegram_id(
        self,
        update: Update,
        context: CallbackContext,
        telegram_id: TelegramId
    ) -> None:
        """
        Отвязывает все Wireguard-конфиги от Telegram ID (tid).
        """
        if not await self.__validate_telegram_id(update, telegram_id):
            return

        if not await self.__check_database_state(update):
            return

        telegram_username = await telegram_utils.get_username_by_id(telegram_id, context)

        if self.database.is_telegram_user_linked(telegram_id):
            if self.database.delete_users_by_telegram_id(telegram_id):
                logger.info(
                    f"Пользователи Wireguard успешно отвязаны от [{telegram_username} ({telegram_id})]."
                )
                if update.message is not None:
                    await update.message.reply_text(
                        f"Пользователи Wireguard успешно отвязаны "
                        f"от [{telegram_username} (<code>{telegram_id}</code>)].",
                        parse_mode='HTML'
                    )
            else:
                logger.info(
                    f"Не удалось отвязать пользователей Wireguard от [{telegram_username} ({telegram_id})]."
                )
                if update.message is not None:
                    await update.message.reply_text(
                        f"Не удалось отвязать пользователей Wireguard "
                        f"от [{telegram_username} (<code>{telegram_id}</code>)].",
                        parse_mode='HTML'
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
                    parse_mode='HTML'
                )


    async def __buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        if await self.__close_button_handler(update, context):
            return True
        
        if update.message is not None and update.message.text == keyboards.BUTTON_UNBIND_FROM_YOURSELF:
            if update.effective_user is not None:
                await self.__delete_message(update, context)
                await self.__unbind_telegram_id(
                    update, context, update.effective_user.id
                )
            return True
        
        return False