from .base import *

class BlockTorrentCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        super().__init__(
            database
        )
        self.command_name = BotCommand.TORRENT_BLOCK
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /block_torrent: блокирует торрент соединения.
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

        logger.info(f"Отправляю ответ на команду [block_torrent] -> Tid [{telegram_id}].")
        
        need_restart_wireguard = False
        try:
            status = wireguard.check_torrent_blocking_status()
            if status == "enabled":
                if update.message is not None:    
                    await update.message.reply_text(
                        "✅ Блокировка торрентов уже включена."
                    )
                    
            elif status == "disabled":
                result = wireguard.add_torrent_blocking()
                if update.message is not None:    
                    await update.message.reply_text(
                        (
                            '🔄 Включаем блокировку торрентов..'
                            f'\n{result.description}'
                        )
                    )
                if result.status is True:
                    need_restart_wireguard = True
                    if update.message is not None:    
                        await update.message.reply_text(
                            (
                                '📋 Новые правила:'
                                f'\n{wireguard.get_current_rules(html_formatting=True).description}'
                            ),
                            parse_mode="HTML"
                        )
                
            else:
                if update.message is not None:    
                    await update.message.reply_text(
                        "❓ Не удалось определить статус. Операция отменена."
                    )
                
        finally:
            await self._end_command(update, context)
        
        return need_restart_wireguard
        