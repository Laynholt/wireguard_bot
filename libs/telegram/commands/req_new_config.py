from .base import *


class RequestNewConfigCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId]
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids
        )
        self.command_name = BotCommands.REQUEST_NEW_CONFIG
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /request_new_config: пользователь запрашивает у админов новый конфиг.
        """
        try:
            if update.effective_user is None:
                if (curr_frame := inspect.currentframe()):
                    logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
                return

            if update.message is not None:
                await update.message.reply_text(
                    "📥 <b>Запрос на конфигурацию WireGuard отправлен.</b>\n\n"
                    "🔄 Ожидайте, пока администратор обработает ваш запрос.\n"
                    "📂 Как только файл будет готов, он будет отправлен вам в этом чате.",
                    parse_mode="HTML"
                )
            
            telegram_id = update.effective_user.id
            telegram_name = await telegram_utils.get_username_by_id(telegram_id, context)

            for admin_id in self.telegram_admin_ids:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=(
                            f"Пользователь [{telegram_name} ({telegram_id})] "
                            f"запросил новый конфиг Wireguard."
                        ),
                    )
                    logger.info(
                        f"Сообщение о запросе нового конфига от [{telegram_name} ({telegram_id})] "
                        f"отправлено админу {admin_id}."
                    )
                except TelegramError as e:
                    logger.error(f"Не удалось отправить сообщение админу {admin_id}: {e}.")
        finally:
            await self._end_command(update, context)