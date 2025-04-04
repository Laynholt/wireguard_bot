from .base import *
from libs.telegram import messages
from libs.wireguard.user_control import sanitize_string


class CommentWireguardUserCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        super().__init__(
            database
        )
    
        self.command_name = BotCommand.COM_UNCOM_USER
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /com_uncom_user: комментирует/раскомментирует (блокирует/разблокирует)
        пользователей Wireguard (путём комментирования в конфиге).
        """
        if update.message is not None:
            await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
        if context.user_data is not None:
            context.user_data[ContextDataKeys.COMMAND] = self.command_name


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Комментирует/Раскомментирует пользователя(-ей) Wireguard.
        """
        try:   
            need_restart_wireguard = False
            
            if context.user_data is None or update.message is None:
                return
            
            entries = update.message.text.split() if update.message.text is not None else []
            
            for entry in entries:
                if await self.__com_user(update, sanitize_string(entry)):
                    need_restart_wireguard = True
        finally:    
            await self._end_command(update, context)
        return need_restart_wireguard


    async def __com_user(self, update: Update, user_name: str) -> bool:
        """
        Комментирует или раскомментирует (блокирует/разблокирует) пользователя Wireguard.
        """
        if not await self._validate_username(update, user_name):
            return False
        
        ret_val = wireguard.comment_or_uncomment_user(user_name)
        if ret_val.status is True:
            logger.info(ret_val.description)
        else:
            logger.error(ret_val.description)
            
        if update.message is not None:
            await update.message.reply_text(ret_val.description)
        
        return ret_val.status