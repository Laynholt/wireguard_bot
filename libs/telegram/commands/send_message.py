from .base import *


class SendMessageCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId],
        telegram_user_ids_cache: set[TelegramId]
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids,
        )
        self.telegram_user_ids_cache = telegram_user_ids_cache
        self.command_name = BotCommands.SEND_MESSAGE
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /send_message: рассылает произвольное сообщение всем зарегистрированным в БД.
        """
        if update.message is not None:
            await update.message.reply_text(
                (
                    "Введите текст для рассылки.\n\n"
                    f"Чтобы отменить ввод, используйте команду /{BotCommands.CANCEL}."
                )
            )
        if context.user_data is not None:
            context.user_data["command"] = self.command_name


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Отправляет сообщение всем пользователям.
        """        
        if update.message is None:
            await self._end_command(update, context)
            return
        
        await self.__send_message_to_all(update, context)
        await self._end_command(update, context)


    async def __send_message_to_all(self, update: Update, context: CallbackContext) -> None:
        """
        Отправляет введённое сообщение всем пользователям, зарегистрированным в БД.
        """
        for tid in self.telegram_user_ids_cache:
            try:
                if update.message is not None:
                    await context.bot.send_message(chat_id=tid, text=update.message.text)
                logger.info(f"Сообщение успешно отправлено пользователю {tid}")
            except TelegramError as e:
                logger.error(f"Не удалось отправить сообщение пользователю {tid}: {e}")
                
                if update.message is not None:
                    telegram_username = await telegram_utils.get_username_by_id(
                        tid, context
                    ) or "Не удалось получить"
                    
                    await update.message.reply_text(
                        f"Не удалось отправить сообщение пользователю "
                        f"{telegram_username} (<code>{tid}</code>): {e}.",
                        parse_mode='HTML'
                    )