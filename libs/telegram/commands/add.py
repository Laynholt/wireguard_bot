from .base import *
from libs.telegram import messages
from libs.telegram.commands.bind import BIND_KEYBOARD

from libs.wireguard.user_control import sanitize_string 


class AddWireguardUserCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        super().__init__(
            database
        )
    
        self.command_name = BotCommand.ADD_USER
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /add_user: добавляет нового пользователя Wireguard.
        """
        if update.message is not None:
            await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
        if context.user_data is not None: 
            context.user_data[ContextDataKeys.COMMAND] = self.command_name
            context.user_data[ContextDataKeys.WIREGUARD_USERS] = []


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Добавляет пользователей Wireguard. Если успешно, сразу отправляет их .zip-конфиг.
        """        
        need_restart_wireguard = False
        
        if context.user_data is None or update.message is None:
            await self._end_command(update, context)
            return
    
        entries = update.message.text.split() if update.message.text is not None else []
        
        for entry in entries:
            if await self.__add_user(
                update, context, sanitize_string(entry)
            ):
                need_restart_wireguard = True
                
        if len(context.user_data[ContextDataKeys.WIREGUARD_USERS]) > 0:
            await update.message.reply_text(
                (
                    f"Нажмите на кнопку '{keyboards.ButtonText.BIND_WITH_TG_USER}', "
                    "чтобы выбрать пользователя Telegram для связывания с переданными конфигами Wireguard.\n\n"
                    f"Для отмены связывания, нажмите кнопку '{keyboards.ButtonText.CANCEL}'."
                ),
                reply_markup=BIND_KEYBOARD.reply_keyboard,
            )
            context.user_data[ContextDataKeys.COMMAND] = BotCommand.BIND_USER
        else:
            await self._end_command(update, context)
        
        return need_restart_wireguard


    async def __add_user(
        self,
        update: Update,
        context: CallbackContext,
        user_name: str
    ) -> bool:
        """
        Добавляет пользователя Wireguard. Если успешно, сразу отправляет ему .zip-конфиг.
        """
        if not await self._validate_username(update, user_name):
            return False

        add_result = wireguard.add_user(user_name)
        if add_result.status:
            zip_result = wireguard.create_zipfile(user_name)
            
            if zip_result.status and update.message is not None:
                await update.message.reply_document(document=open(zip_result.description, "rb"))
                wireguard.remove_zipfile(user_name)
                
                if context.user_data is not None:
                    context.user_data[ContextDataKeys.WIREGUARD_USERS].append(user_name)
            
            logger.info(add_result.description)
        else:
            logger.error(add_result.description)
            
        if update.message is not None:
            await update.message.reply_text(add_result.description)
        return add_result.status