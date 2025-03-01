from .base import *
from asyncio import Semaphore


class ShowWireguardUsersStateCommand(BaseCommand):
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
        self.command_name = BotCommands.SHOW_USERS_STATE
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда /show_users_state: отображает состояние пользователей (активные/отключённые).
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
        active_usernames = sorted(wireguard.get_active_usernames())
        inactive_usernames = sorted(wireguard.get_inactive_usernames())

        linked_dict_tg_wg = telegram_utils.create_linked_dict(linked_users)

        telegram_names_dict = await telegram_utils.get_usernames_in_bulk(
            list(linked_dict_tg_wg.keys()), context, self.semaphore
        )

        linked_dict_wg_tg = {user_name: tid for tid, user_name in linked_users}

        message_parts = []
        message_parts.append(f"<b>🔹 Активные пользователи WG [{len(active_usernames)}] 🔹</b>\n")
        for index, user_name in enumerate(active_usernames, start=1):
            tid = linked_dict_wg_tg.get(user_name, None)
            telegram_info = (
                "Нет привязки"
                if tid is None
                else f'{telegram_names_dict.get(tid) or "Имя пользователя недоступно"} (<code>{tid}</code>)'
            )
            message_parts.append(f"{index}. <code>{user_name}</code> - {telegram_info}\n")

        if inactive_usernames:
            message_parts.append(
                f"\n<b>🔸 Отключенные пользователи WG [{len(inactive_usernames)}] 🔸</b>\n"
            )
            for index, user_name in enumerate(inactive_usernames, start=1):
                tid = linked_dict_wg_tg.get(user_name, None)
                telegram_info = (
                    "Нет привязки"
                    if tid is None
                    else f'{telegram_names_dict.get(tid) or "Имя пользователя недоступно"} (<code>{tid}</code>)'
                )
                message_parts.append(f"{index}. <code>{user_name}</code> - {telegram_info}\n")

        logger.info(
            f"Отправляю информацию об активных и отключенных пользователях -> Tid [{telegram_id}]."
        )
        await telegram_utils.send_long_message(
            update, "".join(message_parts), parse_mode="HTML"
        )
        await self._end_command(update, context)