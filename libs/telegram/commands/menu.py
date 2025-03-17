from .base import *

class MenuCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        super().__init__(
            database
        )
        self.command_name = BotCommand.MENU
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /menu: выводит меню в зависимости от прав пользователя.
        """
        if update.effective_user is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
            return
        
        if context.user_data is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Context user_data is None в функции {curr_frame.f_code.co_name}')
            return
        
        keyboard = keyboards.KEYBOARD_MANAGER.get_keyboard(context.user_data[ContextDataKeys.CURRENT_MENU])
        if keyboard is None:
            logger.error(f'Не удалось найти клавиатуру с индексом {context.user_data[ContextDataKeys.CURRENT_MENU]}')
            return
        
        telegram_id = update.effective_user.id

        logger.info(f"Отправляю ответ на команду [menu] -> Tid [{telegram_id}].")
        if update.message is not None:
            await update.message.reply_text(
                "📌 <b>Выберите команду из меню.</b>",
                reply_markup=keyboard.reply_keyboard,
                parse_mode="HTML"
            )