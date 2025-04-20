from .base import *
from libs.telegram import messages

from telegram import (
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup
)

class GetTelegramIdCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId]
    ) -> None:
        super().__init__(
            database
        )
        self.command_name = BotCommand.GET_TELEGRAM_ID
        self.telegram_admin_ids= telegram_admin_ids
        
        self.keyboard = Keyboard(
            title=BotCommand.GET_TELEGRAM_ID.pretty_text,
            reply_keyboard=ReplyKeyboardMarkup(
                ((
                    KeyboardButton(
                        text=keyboards.ButtonText.TELEGRAM_USER.value.text,
                        request_users=KeyboardButtonRequestUsers(
                            request_id=0,
                            user_is_bot=False,
                            request_username=True,
                        )
                    ),
                    keyboards.ButtonText.OWN.value.text
                    ), (
                        keyboards.ButtonText.CANCEL.value.text,
                    )
                ),
                one_time_keyboard=True
            )
        )
        self.keyboard.add_parent(keyboards.TELEGRAM_INFO_KEYBOARD)

    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /get_telegram_id: выводит Telegram ID пользователя.
        Если пользователь администратор — позволяет узнать Telegram ID других пользователей.
        """
        if update.effective_user is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
            return

        if update.message is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
            return
        
        if self.keyboard is None:
            return
        
        telegram_id = update.effective_user.id
        if telegram_id in self.telegram_admin_ids:
            if context.user_data is not None:
                context.user_data[ContextDataKeys.COMMAND] = self.command_name
            
            message=(
                "Выберете, чей Telegram ID хотите получить.\n\n"
                f"Для отмены действия нажмите кнопку '{keyboards.ButtonText.CANCEL}'."
            )    
            
            await update.message.reply_text(
                message,
                reply_markup=self.keyboard.reply_keyboard
            )
        else:
            await self.__get_own_tid(update, context)
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /get_telegram_id: выводит Telegram ID пользователя.
        """
        if await self._buttons_handler(update, context):
            return
        
        try:
            if context.user_data is None or update.message is None:
                return
        
            if update.message.users_shared is not None:
                message_parts = [
                    f"<b>📋 Telegram ID</b>\n\n"
                ]
                for index, shared_user in enumerate(update.message.users_shared.users, start=1):
                    message_parts += [
                        f"{index}. <code>{shared_user.user_id}</code>"
                    ]
                    
                await telegram_utils.send_long_message(
                    update, message_parts, parse_mode="HTML"
                )
        finally:
            await self._end_command(update, context)


    async def __get_own_tid(self, update: Update, context: CallbackContext) -> None:
        try:
            if update.effective_user is None:
                if (curr_frame := inspect.currentframe()):
                    logger.error(
                        f'Update effective_user is None в функции {curr_frame.f_code.co_name}'
                    )
                return
            
            telegram_id = update.effective_user.id

            logger.info(f"Отправляю ответ на команду [get_telegram_id] -> Tid [{telegram_id}].")
            if update.message is not None:
                await update.message.reply_text(
                    f"🆔 Ваш идентификатор: <code>{telegram_id}</code>.", parse_mode="HTML"
                )
        finally:
            await self._end_command(update, context)
            
    
    async def _buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        if await self._cancel_button_handler(update, context):
            await self._end_command(update, context)
            return True
        
        if (
            update.message is not None
            and update.message.text == keyboards.ButtonText.OWN
        ):
            await self._delete_message(update, context)
            await self.__get_own_tid(update, context)
            return True
        
        return False