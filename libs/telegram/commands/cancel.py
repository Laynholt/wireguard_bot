from .base import *


class CancelCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId]
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids
        )
        self.command_name = BotCommand.CANCEL
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /cancel: универсальная отмена действия для администратора.
        """
        if update.message is not None:
            await update.message.reply_text(
                f"Действие отменено. Можете начать сначала, выбрав команду из меню (/{BotCommand.MENU}).",
                reply_markup=keyboards.ADMIN_MENU,
            )
        if context.user_data is not None:
            context.user_data["command"] = None
            context.user_data["wireguard_users"] = []