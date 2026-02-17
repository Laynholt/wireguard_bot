import asyncio

from .base import *
from libs.telegram import messages
from libs.wireguard.user_control import sanitize_string


class RemoveWireguardUserCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        super().__init__(
            database
        )
    
        self.command_name = BotCommand.REMOVE_USER
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /remove_user: удаляет существующего пользователя Wireguard.
        """
        if update.message is not None:
            await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
        if context.user_data is not None:
            context.user_data[ContextDataKeys.COMMAND] = self.command_name


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Удаляет пользователя(-ей) Wireguard.
        """
        try:
            need_restart_wireguard = False
            
            if context.user_data is None or update.message is None:
                return
            
            entries = update.message.text.split() if update.message.text is not None else []
            
            for entry in entries:
                if await self.__rem_user(update, sanitize_string(entry)):
                    need_restart_wireguard = True
        finally:
            await self._end_command(update, context)
        return need_restart_wireguard


    async def __rem_user(self, update: Update, user_name: str) -> bool:
        """
        Удаляет пользователя Wireguard, а также запись о нём из БД (если есть).
        """
        if not await self._validate_username(update, user_name):
            return False

        remove_result = await asyncio.to_thread(wireguard.remove_user, user_name)
        if remove_result.status:
            logger.info(remove_result.description)
            if await self._check_database_state(update):
                if not self.database.delete_user(user_name):
                    logger.error(f"Не удалось удалить информацию о пользователе [{user_name}] из базы данных.")
                    
                    if update.message is not None:
                        await update.message.reply_text(
                            f"Не удалось удалить информацию о пользователе [{user_name}] из базы данных."
                        )
                else:
                    logger.info(f"Пользователь [{user_name}] удален из базы данных.")
        else:
            logger.error(remove_result.description)
        
        if update.message is not None:
            await update.message.reply_text(remove_result.description)
        
        return remove_result.status
