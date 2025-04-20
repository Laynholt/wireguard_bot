from .base import *
from libs.telegram import messages
from libs.telegram.types import TelegramUserName
from libs.wireguard.user_control import sanitize_string


class GetTelegramUsernameByIdCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        super().__init__(
            database
        )
        self.command_name = BotCommand.GET_TELEGRAM_USERNAME
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /get_telegram_username: выводит имя Telegram пользователя по его Telegram ID.
        """
        if update.message is not None:
            await update.message.reply_text(messages.ENTER_TELEGRAM_IDS_MESSAGE)
        if context.user_data is not None: 
            context.user_data[ContextDataKeys.COMMAND] = self.command_name

    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /get_telegram_username: выводит имя Telegram пользователя по его Telegram ID.
        """
        if context.user_data is None or update.message is None:
            await self._end_command(update, context)
            return
    
        entries = update.message.text.split() if update.message.text is not None else []
        
        if entries:
            message_parts = [
                f"<b>📋 Имена пользователей Telegram</b>\n\n"
            ]
            for index, entry in enumerate(entries, start=1):
                telegram_username = await self.__get_tg_username_by_id(
                    update, context, sanitize_string(entry)
                )
                
                if telegram_username is not None:
                    message_parts += [
                        f"{index}. {telegram_username} (<code>{entry}</code>)"
                    ]

            if len(message_parts) > 1:
                await telegram_utils.send_long_message(
                        update, message_parts, parse_mode="HTML"
                    )        
        await self._end_command(update, context)
        

    async def __get_tg_username_by_id(
        self, 
        update: Update,
        context: CallbackContext,
        telegram_id: str
    ) -> Optional[TelegramUserName]:
        """
        Отправляет имя Telegram пользователя по переданному Telegram ID
        """
        if update.message is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
            return
        
        if not await self._validate_telegram_id(update, telegram_id):
            return
        
        tid = int(telegram_id)
        telegram_username = await telegram_utils.get_username_by_id(tid, context)
        
        return telegram_username or 'Имя пользователя недоступно'