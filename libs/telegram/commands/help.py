from .base import *
from libs.telegram import messages


class HelpCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId]
    ) -> None:
        super().__init__(
            database
        )
        self.command_name = BotCommand.HELP
        self.telegram_admin_ids = telegram_admin_ids
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /help: показывает помощь по доступным командам.
        """
        if update.effective_user is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
            return
        
        if context.user_data is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Context user_data is None в функции {curr_frame.f_code.co_name}')
            return
        
        keyboard = keyboards.KEYBOARD_MANAGER.get_keyboard(context.user_data[ContextDataKeys.CURRENT_MENU])
        if keyboard is None:
            logger.error(f'Не удалось найти клавиатуру с индексом {context.user_data[ContextDataKeys.CURRENT_MENU]}')
            return
        
        telegram_id = update.effective_user.id

        logger.info(f"Отправляю ответ на команду [help] -> Tid [{telegram_id}].")
        if update.message is not None:
            is_admin = telegram_id in self.telegram_admin_ids
            await update.message.reply_text(
                messages.ADMIN_HELP if is_admin else messages.USER_HELP,
                reply_markup=keyboard.reply_keyboard,
                parse_mode="HTML"
            )