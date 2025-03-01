from .base import *
from libs.wireguard import stats as wireguard_stats

from asyncio import Semaphore


class GetAllWireguardUsersStatsCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId],
        semaphore: Semaphore,
        wireguard_config_path: str,
        wireguard_log_path: str
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids
        )
        self.command_name = BotCommands.GET_ALL_STATS
        self.semaphore = semaphore
        self.wireguard_config_path = wireguard_config_path
        self.wireguard_log_path = wireguard_log_path
    
    
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда для администраторов.
        Выводит статистику для всех конфигов WireGuard, включая информацию о владельце
        (Telegram ID и username). Если владелец не привязан, выводит соответствующую пометку.
        """
        try:
            if update.message is None:
                if (curr_frame := inspect.currentframe()):
                    logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
                return
            
            # Сначала получаем всю статистику
            all_wireguard_stats = wireguard_stats.accumulate_wireguard_stats(
                conf_file_path=self.wireguard_config_path,
                json_file_path=self.wireguard_log_path,
                sort_by=wireguard_stats.SortBy.TRANSFER_SENT,
            )

            if not all_wireguard_stats:
                await update.message.reply_text("Нет данных по ни одному конфигу.")
                return

            if not await self._check_database_state(update):
                return

            # Получаем все связки (владелец <-> конфиг)
            linked_users = self.database.get_all_linked_data()
            linked_dict = {user_name: tid for tid, user_name in linked_users}

            # Достаем username для всех владельцев (bulk-запрос)
            linked_telegram_ids = set(linked_dict.values())
            linked_telegram_names_dict = await telegram_utils.get_usernames_in_bulk(
                linked_telegram_ids, context, self.semaphore
            )

            lines = []
            inactive_usernames = wireguard.get_inactive_usernames()
            
            for i, (wg_user, user_data) in enumerate(all_wireguard_stats.items(), start=1):
                owner_tid = linked_dict.get(wg_user)
                if owner_tid is not None:
                    owner_username = linked_telegram_names_dict.get(owner_tid)
                    owner_part = (
                        f"   👤 <b>Владелец:</b>\n"
                        f"      ├ 🆔 <b>ID:</b> <code>{owner_tid}</code>\n"
                        f"      └ 🔗 <b>Telegram:</b> "
                        f"{'Не удалось получить' if owner_username is None else owner_username}"
                    )
                else:
                    owner_part = "   👤 <b>Владелец:</b>\n      └ 🚫 <i>Не назначен</i>"

                lines.append(
                    f"\n<b>{i}]</b> <b>🌐 Конфиг:</b> <i>{wg_user}</i> "
                    f"{'🔴 <b>[Неактивен]</b>' if wg_user in inactive_usernames else '🟢 <b>[Активен]</b>'}\n"
                    f"   {owner_part}\n"
                    f"   📡 IP: {user_data.allowed_ips}\n"
                    f"   📤 Отправлено: {user_data.transfer_received if user_data.transfer_received else 'N/A'}\n"
                    f"   📥 Получено: {user_data.transfer_sent if user_data.transfer_sent else 'N/A'}\n"
                    f"   ━━━━━━━━━━━━━━━━"
                )

            tid = -1
            if update.effective_user is not None:
                tid = update.effective_user.id
            
            logger.info(f"Отправляю статистику по всем конфигам Wireguard -> Tid [{tid}].")
            
            # Разбиваем на батчи по указанному размеру
            batch_size = 5
            batched_lines = [
                lines[i:i + batch_size]
                for i in range(0, len(lines), batch_size)
            ]
            
            await telegram_utils.send_batched_messages(
                update=update,
                batched_lines=batched_lines,
                parse_mode="HTML",
                groups_before_delay=2,
                delay_between_groups=0.5
            )

        finally:
            await self._end_command(update, context)