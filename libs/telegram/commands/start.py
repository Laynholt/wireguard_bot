from .base import *
from libs.telegram import messages


class StartCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId],
        telegram_user_ids_cache: set[TelegramId]
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids
        )
        self.telegram_user_ids_cache = telegram_user_ids_cache
        self.command_name = BotCommands.START
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /start: приветствие и первичная регистрация пользователя в базе.
        """
        if update.effective_user is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
            return
        
        telegram_id = update.effective_user.id
        if not await self.__ensure_user_exists(telegram_id, update):
            return
        
        if telegram_id not in self.telegram_user_ids_cache:
            telegram_username = telegram_utils.get_username_by_id(telegram_id, context)
            text = (
                update.message.text
                if update.message is not None and update.message.text is not None
                else ''
            )
            logger.info(
                f'Обращение от заблокированного пользователя: {telegram_username} ({telegram_id})'
                f' с текстом: [{text}].'
            )
            return

        logger.info(f"Отправляю ответ на команду [start] -> Tid [{telegram_id}].")
        if update.message is not None:
            await update.message.reply_text(
                messages.ADMIN_HELLO
                if telegram_id in self.telegram_admin_ids
                else messages.USER_HELLO,
                parse_mode="HTML"
            )
    

    async def __ensure_user_exists(self, telegram_id: TelegramId, update: Update) -> bool:
        """
        Проверяет состояние базы данных. Если она загружена, убеждается,
        что пользователь Telegram существует в базе. Если нет — добавляет.
        """
        if not await self._check_database_state(update):
            return False

        if not self.database.is_telegram_user_exists(telegram_id):
            logger.info(f"Добавляю нового участника Tid [{telegram_id}].")
            self.database.add_telegram_user(telegram_id)
            self.telegram_user_ids_cache.add(telegram_id)
        return True