from .base import *

class GetTorrentStateCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        super().__init__(
            database
        )
        self.command_name = BotCommand.TORRENT_STATE
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /get_torrent_state: выводит статус блокировки торрентов.
        """
        if update.effective_user is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
            return
        
        if context.user_data is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Context user_data is None в функции {curr_frame.f_code.co_name}')
            return
         
        telegram_id = update.effective_user.id

        logger.info(f"Отправляю ответ на команду [get_torrent_state] -> Tid [{telegram_id}].")
        
        try:
            if update.message is not None:
                status = wireguard.check_torrent_blocking_status()
                if status == "enabled":
                    status = "✅ Блокировка торрентов включена"
                elif status == "disabled":
                    status = "❌ Блокировка торрентов отключена"
                else:
                    status = "❓ Не удалось определить статус"
                
                await update.message.reply_text(
                    f"<b>🔍 Проверяем статус блокировки торрентов:</b>\n{status}.",
                    parse_mode="HTML"
                )
                
        finally:
            await self._end_command(update, context)