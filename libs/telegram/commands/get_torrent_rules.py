from .base import *

class GetTorrentRulesCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        super().__init__(
            database
        )
        self.command_name = BotCommand.TORRENT_RULES
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /get_torrent_rules: показывает текущие правила отправки пакетов через Wireguard.
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

        logger.info(f"Отправляю ответ на команду [get_torrent_rules] -> Tid [{telegram_id}].")
        
        try:
            if update.message is not None:
                await update.message.reply_text(
                    wireguard.get_current_rules(html_formatting=True).description,
                    parse_mode="HTML"
                )
                
        finally:
            await self._end_command(update, context)