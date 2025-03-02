from .base import *
from libs.telegram import messages


class HelpCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId]
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids
        )
        self.command_name = BotCommand.HELP
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /help: показывает помощь по доступным командам.
        """
        if update.effective_user is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
            return
        
        telegram_id = update.effective_user.id

        logger.info(f"Отправляю ответ на команду [help] -> Tid [{telegram_id}].")
        if update.message is not None:
            is_admin = telegram_id in self.telegram_admin_ids
            await update.message.reply_text(
                messages.ADMIN_HELP if is_admin else messages.USER_HELP,
                reply_markup=keyboards.ADMIN_MENU if is_admin else keyboards.USER_MENU,
                parse_mode="HTML"
            )