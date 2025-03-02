from .base import *


class ReloadWireguardServerCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId]
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids
        )
        self.command_name = BotCommand.RELOAD_WG_SERVER
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Обработчик команды перезагрузки сервера Wireguard.
        """
        if update.message is not None:
            await update.message.reply_text("🔄 Перезагружаю сервер WireGuard...")
        
        try:
            # await asyncio.to_thread(wireguard_utils.log_and_restart_wireguard)
            success = await wireguard_utils.async_restart_wireguard()
            response = (
                "✅ Сервер WireGuard успешно перезагружен!"
                if success
                else "❌ Ошибка! Не удалось перезагрузить Wireguard!"
            )
        except Exception as e:
            response = f"⚠️ Ошибка: {str(e)}"
          
        if update.message is not None:
            await update.message.reply_text(response)

        await self._end_command(update, context)