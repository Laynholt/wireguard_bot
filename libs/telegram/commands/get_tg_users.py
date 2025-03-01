from .base import *
from asyncio import Semaphore

class GetTelegramUsersCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId],
        semaphore: Semaphore
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids
        )
        self.semaphore = semaphore
        self.command_name = BotCommands.GET_TELEGRAM_USERS
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /get_telegram_users: выводит всех телеграм-пользователей, которые
        взаимодействовали с ботом (есть в БД).
        """
        try:
            if update.effective_user is None:
                if (curr_frame := inspect.currentframe()):
                    logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
                return
            
            telegram_id = update.effective_user.id
            if not self.database.db_loaded:
                logger.error("Ошибка! База данных не загружена!")
                if update.message is not None:
                    await update.message.reply_text("Не удалось получить данные из базы данных.")
                return

            telegram_info = {tid: status for tid, status in self.database.get_all_telegram_users()}
            logger.info(f"Отправляю список телеграм-пользователей -> Tid [{telegram_id}].")

            if not telegram_info:
                if update.message is not None:
                    await update.message.reply_text("У бота пока нет активных Telegram пользователей.")
                return

            telegram_usernames = await telegram_utils.get_usernames_in_bulk(
                telegram_info.keys(), context, self.semaphore
            )

            message_parts = [
                f"<b>📋 Telegram Id всех пользователей бота [{len(telegram_info)}]</b>\n"
                f"<em>Значком 🚩 обозначены заблокированные пользователи.</em>\n\n"
            ]
            message_parts += [
                f"{index}. {telegram_usernames.get(tid) or 'Имя пользователя недоступно'} (<code>{tid}</code>)"
                f"{' 🚩' if status else ''}\n"
                for index, (tid, status) in enumerate(telegram_info.items(), start=1)
            ]

            await telegram_utils.send_long_message(
                update, message_parts, parse_mode="HTML"
            )

        finally:
            await self._end_command(update, context)