from .base import *


class CancelCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        super().__init__(
            database
        )
        self.command_name = BotCommand.CANCEL
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /cancel: универсальная отмена действия для администратора.
        """
        if context.user_data is None:
            return
        
        keyboard = keyboards.KEYBOARD_MANAGER.get_keyboard(context.user_data[ContextDataKeys.CURRENT_MENU])
        if keyboard is None:
            logger.error(f'Не удалось найти клавиатуру с индексом {context.user_data[ContextDataKeys.CURRENT_MENU]}')
            return
        
        if update.message is not None:
            await update.message.reply_text(
                f"Действие отменено. Можете начать сначала, выбрав команду из меню (/{BotCommand.MENU}).",
                reply_markup=keyboard.reply_keyboard,
            )
        if context.user_data is not None:
            context.user_data[ContextDataKeys.COMMAND] = None
            context.user_data[ContextDataKeys.WIREGUARD_USERS] = []