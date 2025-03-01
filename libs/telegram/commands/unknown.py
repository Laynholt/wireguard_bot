from .base import *


class UnknownCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId]
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids
        )
        self.command_name = BotCommands.HELP
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Обработчик неизвестных команд.
        """
        if update.message is not None:
            await update.message.reply_text(
                f"Неизвестная команда. Используйте /{BotCommands.HELP}"
                " для просмотра доступных команд."
            )