from .base import *


class GetTelegramIdCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        super().__init__(
            database
        )
        self.command_name = BotCommand.GET_TELEGRAM_ID
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /get_telegram_id: выводит телеграм-ID пользователя.
        """
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