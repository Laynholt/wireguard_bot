from .base import *
from libs.telegram import messages


class UnbindWireguardUserCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId]
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids,
        )
    
        self.command_name = BotCommands.UNBIND_USER
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /unbind_user: отвязывает конфиги Wireguard от Telegram-пользователя (по user_name).
        """
        if update.message is not None:
            await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
        if context.user_data is not None:
            context.user_data["command"] = self.command_name


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Отвязывает пользователя(-ей) Wireguard от Telegram Id.
        """        
        if context.user_data is None or update.message is None:
            return
        
        entries = update.message.text.split() if update.message.text is not None else []
        
        for entry in entries:
            await self.__unbind_user(update, entry)
        await self.__end_command(update, context)


    async def __unbind_user(self, update: Update, user_name: str) -> None:
        """
        Отвязывает пользователя Wireguard по его user_name (если есть в БД).
        """
        if not await self.__validate_username(update, user_name):
            return

        if not await self.__check_database_state(update):
            return

        if self.database.is_user_exists(user_name):
            if self.database.delete_user(user_name):
                logger.info(f"Пользователь [{user_name}] успешно отвязан.")
                if update.message is not None:
                    await update.message.reply_text(f"Пользователь [{user_name}] успешно отвязан.")
            else:
                logger.error(f"Не удалось отвязать пользователя [{user_name}].")
                if update.message is not None:
                    await update.message.reply_text(f"Не удалось отвязать пользователя [{user_name}].")
        else:
            logger.info(f"Пользователь [{user_name}] не привязан ни к одному Telegram ID в базе данных.")
            if update.message is not None:
                await update.message.reply_text(
                    f"Пользователь [{user_name}] не привязан ни к одному Telegram ID в базе данных."
                )