from .base import *

class MenuCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId]
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids
        )
        self.command_name = BotCommand.MENU
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /menu: выводит меню в зависимости от прав пользователя.
        """
        if update.effective_user is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
            return
        
        telegram_id = update.effective_user.id

        logger.info(f"Отправляю ответ на команду [menu] -> Tid [{telegram_id}].")
        if update.message is not None:
            await update.message.reply_text(
                "📌 <b>Выберите команду из меню.</b>",
                reply_markup=(
                    keyboards.ADMIN_MENU
                    if telegram_id in self.telegram_admin_ids
                    else keyboards.USER_MENU
                ),
                parse_mode="HTML"
            )