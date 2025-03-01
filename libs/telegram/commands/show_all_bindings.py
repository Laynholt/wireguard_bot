from .base import *
from asyncio import Semaphore


class ShowAllBindingsCommand(BaseCommand):
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
        self.command_name = BotCommands.SHOW_ALL_BINDINGS
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /show_all_bindings: показывает все привязки:
        - Какие пользователи Wireguard привязаны к каким Telegram ID,
        - Список непривязанных Telegram ID,
        - Список непривязанных user_name.
        """
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

        linked_users = self.database.get_all_linked_data()
        telegram_info = {tid: status for tid, status in self.database.get_all_telegram_users()}
        available_usernames = wireguard.get_usernames()

        # Словарь вида {telegram_id: [user_names]}
        linked_dict = telegram_utils.create_linked_dict(linked_users)

        # Определяем всех Telegram-пользователей, у которых есть привязки
        linked_telegram_ids = list(linked_dict.keys())
        linked_telegram_names_dict = await telegram_utils.get_usernames_in_bulk(
            linked_telegram_ids, context, self.semaphore
        )

        message_parts = []
        if linked_telegram_ids:
            message_parts.append(f"<b>🔹🔐 Привязанные пользователи [{len(linked_dict)}] 🔹</b>\n")
            for index, (tid, user_names) in enumerate(linked_dict.items(), start=1):
                user_names_str = ", ".join([f"<code>{u}</code>" for u in sorted(user_names)])
                telegram_username = linked_telegram_names_dict.get(tid) or "Имя пользователя недоступно"
                message_parts.append(f"{index}. {telegram_username} ({tid}): {user_names_str}\n")

        # Непривязанные Telegram ID
        unlinked_telegram_ids = set(telegram_info.keys()) - set(linked_telegram_ids)
        if unlinked_telegram_ids:
            unlinked_telegram_names_dict = await telegram_utils.get_usernames_in_bulk(
                list(unlinked_telegram_ids), context, self.semaphore
            )
            message_parts.append(
                f"\n<b>🔹❌ Непривязанные Telegram Id [{len(unlinked_telegram_ids)}] 🔹</b>\n"
            )
            for index, tid in enumerate(unlinked_telegram_ids, start=1):
                telegram_username = unlinked_telegram_names_dict.get(tid) or "Имя пользователя недоступно"
                message_parts.append(f"{index}. {telegram_username} ({tid})\n")

        # Непривязанные user_name
        linked_usernames = {u for _, u in linked_users}
        unlinked_usernames = set(available_usernames) - linked_usernames
        if unlinked_usernames:
            message_parts.append(
                f"\n<b>🔹🛡️ Непривязанные конфиги Wireguard [{len(unlinked_usernames)}] 🔹</b>\n"
            )
            for index, user_name in enumerate(sorted(unlinked_usernames), start=1):
                message_parts.append(f"{index}. <code>{user_name}</code>\n")

        logger.info(
            f"Отправляю информацию о привязанных и непривязанных пользователях -> Tid [{telegram_id}]."
        )
        await telegram_utils.send_long_message(
            update, "".join(message_parts), parse_mode="HTML"
        )
        await self._end_command(update, context)