from curses.ascii import isdigit
from typing import final
from .base import *
from libs.telegram import messages
from libs.wireguard import stats as wireguard_stats
from libs.wireguard import wg_db
from datetime import datetime

from telegram import (
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup
)
from libs.wireguard.user_control import sanitize_string


class GetWireguardUserStatsCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        wireguard_config_path: str,
        return_own_stats: bool
    ) -> None:
        super().__init__(
            database
        )
    
        self.command_name = BotCommand.GET_MY_STATS if return_own_stats else BotCommand.GET_USER_STATS
        self.keyboard = Keyboard(
            title=BotCommand.GET_MY_STATS.pretty_text if return_own_stats else BotCommand.GET_USER_STATS.pretty_text,
            reply_keyboard=ReplyKeyboardMarkup(
                ((
                    KeyboardButton(
                        text=keyboards.ButtonText.TELEGRAM_USER.value.text,
                        request_users=KeyboardButtonRequestUsers(
                            request_id=0,
                            user_is_bot=False,
                            request_username=True,
                        )
                    ),
                    keyboards.ButtonText.WIREGUARD_USER.value.text
                    ), (
                        keyboards.ButtonText.CANCEL.value.text,
                    )
                ),
                one_time_keyboard=True
            )
        )
        self.keyboard.add_parent(keyboards.WIREGUARD_STATS_KEYBOARD)
        
        self.wireguard_config_path = wireguard_config_path
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /get_user_stats: выводит статистику для конкретного пользователя
        телеграмм или конкретного конфига WireGuard.
        
        Команда /get_my_stats: выводит статистику по вашим конфигам WireGuard.
        """
        if self.command_name == BotCommand.GET_MY_STATS:
            if update.effective_user is None:
                if (curr_frame := inspect.currentframe()):
                    logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
                return
            
            telegram_id = update.effective_user.id
            
            if context.user_data is not None:
                context.user_data[ContextDataKeys.WIREGUARD_USERS] = []
            
            await self._create_list_of_wireguard_users_by_telegram_id(
                update, context, telegram_id
            )
            await self.__get_user_stats(update, context, own_stats=True)
            await self._end_command(update, context)

        # Иначе /get_user_stats
        else:
            if self.keyboard is None:
                return
            
            if update.message is not None:
                await update.message.reply_text(
                    text=(
                        "Выберете, чью статистику вы хотите получить.\n\n"
                        f"Для отмены нажмите кнопку {keyboards.ButtonText.CANCEL}."
                    ),
                    reply_markup=self.keyboard.reply_keyboard
                )
            if context.user_data is not None:
                context.user_data[ContextDataKeys.COMMAND] = self.command_name
                context.user_data[ContextDataKeys.WIREGUARD_USERS] = []


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Возвращает список пользователей Wireguard, привязанных к данному Telegram.
        """
        if await self._buttons_handler(update, context):
            return
        
        try:
            if context.user_data is None or update.message is None:
                return
        
            if update.message.users_shared is not None:
                for shared_user in update.message.users_shared.users:
                    await self._create_list_of_wireguard_users_by_telegram_id(
                        update,
                        context,
                        shared_user.user_id
                    )
            else:                
                entries = update.message.text.split() if update.message.text is not None else []
                for entry in entries:
                    if entry.isdigit():
                        await self._create_list_of_wireguard_users_by_telegram_id(
                            update,
                            context,
                            int(entry)
                        )
                    else:
                        await self._create_list_of_wireguard_users(
                            update, context, sanitize_string(entry)
                        )

            await self.__get_user_stats(update, context)
        finally:
            await self._end_command(update, context)


    async def __get_user_stats(self, update: Update, context: CallbackContext, own_stats: bool = False) -> None:
        """
        Выводит статистику по переданным WireGuard конфигам в context'е.
        Если конфиг недоступен или отсутствует (удалён), информация об этом
        выводится в сообщении. При необходимости лишние записи удаляются из БД.
        """
        if update.effective_user is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
            return
        
        if update.message is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
            return
        
        if context.user_data is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Context user_data is None в функции {curr_frame.f_code.co_name}')
            return
        
        telegram_id = update.effective_user.id

        if not await self._check_database_state(update):
            return

        wireguard_users = context.user_data[ContextDataKeys.WIREGUARD_USERS]
        if not wireguard_users:
            if own_stats:
                await update.message.reply_text(
                    "📁 <b>У вас нет доступных конфигураций WireGuard.</b>\n\n"
                    f"📝 <em>Используйте /{BotCommand.REQUEST_NEW_CONFIG}, чтобы отправить запрос "
                    f"администратору на создание новой конфигурации.</em>",
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    "ℹ️ <b>Статистика для заданного пользователя Telegram "
                    "или пользователей WireGuard отсутствует.</b>\n\n",
                    parse_mode="HTML"
                )
            return

        # Получаем полную статистику
        all_wireguard_stats = wireguard_stats.accumulate_wireguard_stats(
            conf_file_path=self.wireguard_config_path,
            sort_by=wireguard_stats.SortBy.TRANSFER_SENT,
        )
        
        if not all_wireguard_stats:
            await update.message.reply_text("Нет данных по ни одному конфигу.")
            return

        # Сортируем список пользователей по общему трафику (sent + received), по убыванию
        def _total_bytes(user: str) -> int:
            data = all_wireguard_stats.get(user)
            if data is None:
                return 0
            return (
                wireguard_stats.human_to_bytes(data.transfer_sent)
                + wireguard_stats.human_to_bytes(data.transfer_received)
            )

        wireguard_users.sort(key=_total_bytes, reverse=True)

        # Агрегация суммарной статистики по владельцам
        summary_by_owner: dict[int, dict[str, int]] = {}

        lines = []
        inactive_usernames = wireguard.get_inactive_usernames()
        
        username_cache: dict[int, Optional[str]] = {}

        for i, wg_user in enumerate(wireguard_users, start=1):
            user_data = all_wireguard_stats.get(wg_user, None)
            created_at_human = "N/A"
            db_row = wg_db.get_user(wg_user)
            if db_row is not None:
                created_raw = db_row["created_at"] if "created_at" in db_row.keys() else None
                if created_raw:
                    try:
                        created_at_human = datetime.fromisoformat(created_raw).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        created_at_human = created_raw

            # Случай, когда статистики для пользователя нет
            # Это может быть только в том случае, если она отсутствует в логах, 
            # а также нам не удалось получить для него данные из текущего docker exec.
            
            # Причиной может быть отсутствие записи пользователя в wg0.conf, поэтому
            # лучше удалить его, раз он как-то некорректно создался, либо когда-то неправильно удалился. 
            if user_data is None:
                # Проверяем, существует ли конфиг этого пользователя фактически
                check_result = wireguard.check_user_exists(wg_user)
                if check_result.status:
                    remove_result = wireguard.remove_user(wg_user)
                    if remove_result.status:
                        logger.info(remove_result.description)
                    else:
                        logger.error(remove_result.description)

                # Если пользователь есть в БД, но конфиг отсутствует — удаляем из БД
                if self.database.delete_user(wg_user):
                    logger.info(f"Пользователь [{wg_user}] удалён из базы данных.")
                else:
                    logger.error(
                        f"Не удалось удалить информацию о пользователе [{wg_user}] из базы данных."
                    )

                continue

            # Если всё в порядке, формируем строку со статистикой
            day_stat = wireguard_stats.get_period_usage(user_data, wireguard_stats.Period.DAILY)
            week_stat = wireguard_stats.get_period_usage(user_data, wireguard_stats.Period.WEEKLY)
            month_stat = wireguard_stats.get_period_usage(user_data, wireguard_stats.Period.MONTHLY)
            handshake_text = wireguard_stats.format_handshake_age(user_data)
            endpoint_last_seen_text = wireguard_stats.get_current_endpoint_last_seen_text(user_data)
            other_endpoint_ips = wireguard_stats.get_other_endpoint_ips_with_last_seen(user_data)
            other_endpoint_text = (
                ", ".join([f"{ip} ({seen_at})" for ip, seen_at in other_endpoint_ips])
                if other_endpoint_ips else
                "нет"
            )

            # Определяем владельца конкретного конфига
            owner_tid_list = self.database.get_telegram_id_by_user(wg_user)
            owner_tid_local = owner_tid_list[0] if owner_tid_list else None
            if owner_tid_local is not None and own_stats is False:
                if owner_tid_local not in username_cache:
                    username_cache[owner_tid_local] = await telegram_utils.get_username_by_id(owner_tid_local, context)
                owner_username = username_cache[owner_tid_local]
                owner_part = (
                    f"   👤 <b>Владелец:</b>\n"
                    f"      ├ 🆔 <b>ID:</b> <code>{owner_tid_local}</code>\n"
                    f"      └ 🔗 <b>Telegram:</b> "
                    f"{'Не удалось получить' if owner_username is None else owner_username}"
                )
            else:
                owner_part = "   👤 <b>Владелец:</b>\n      └ 🚫 <i>Не назначен</i>"
            owner_part = "" if own_stats else f"   {owner_part}\n"

            # Накопим агрегированные значения по владельцу
            if owner_tid_local is not None:
                agg = summary_by_owner.setdefault(owner_tid_local, {
                    "count": 0,
                    "total_sent": 0,
                    "total_recv": 0,
                    "day_sent": 0,
                    "day_recv": 0,
                    "week_sent": 0,
                    "week_recv": 0,
                    "month_sent": 0,
                    "month_recv": 0,
                })
                agg["count"] += 1
                agg["total_sent"] += wireguard_stats.human_to_bytes(user_data.transfer_sent)
                agg["total_recv"] += wireguard_stats.human_to_bytes(user_data.transfer_received)
                agg["day_sent"] += day_stat.sent_bytes
                agg["day_recv"] += day_stat.received_bytes
                agg["week_sent"] += week_stat.sent_bytes
                agg["week_recv"] += week_stat.received_bytes
                agg["month_sent"] += month_stat.sent_bytes
                agg["month_recv"] += month_stat.received_bytes

            lines.append(
                f"\n<b>{i}]</b> <b>🌐 Конфиг:</b> <i>{wg_user}</i> "
                f"{'🔴 <b>[Неактивен]</b>' if wg_user in inactive_usernames else '🟢 <b>[Активен]</b>'}\n"
                f"{owner_part}"
                f"   🗓️ Создан: {created_at_human}\n"
                f"   📡 IP: {user_data.allowed_ips}\n"
                f"   🌍 Последний endpoint: {user_data.endpoint or 'N/A'} ({endpoint_last_seen_text})\n"
                f"   🧭 Другие endpoint IP: {other_endpoint_text}\n"
                f"   ⏱️ Последнее рукопожатие: {handshake_text if handshake_text else 'N/A'}\n"
                f"   📊 Статистика по трафику:\n"
                f"      За сутки: ↑ {wireguard_stats.bytes_to_human(day_stat.sent_bytes)} | ↓ {wireguard_stats.bytes_to_human(day_stat.received_bytes)}\n"
                f"      За неделю: ↑ {wireguard_stats.bytes_to_human(week_stat.sent_bytes)} | ↓ {wireguard_stats.bytes_to_human(week_stat.received_bytes)}\n"
                f"      За месяц: ↑ {wireguard_stats.bytes_to_human(month_stat.sent_bytes)} | ↓ {wireguard_stats.bytes_to_human(month_stat.received_bytes)}\n"
                f"      Всего: ↑ {user_data.transfer_sent or '0 B'} | ↓ {user_data.transfer_received or '0 B'}\n"
                f"   ━━━━━━━━━━━━━━━━"
            )

        logger.info(f"Отправляю статистику по личным конфигам Wireguard -> Tid [{telegram_id}].")

        # Суммарное сообщение по владельцам с несколькими конфигами
        for owner_tid_local, agg in summary_by_owner.items():
            if agg["count"] <= 1:
                continue
            if owner_tid_local not in username_cache:
                username_cache[owner_tid_local] = await telegram_utils.get_username_by_id(owner_tid_local, context) if owner_tid_local else None
            owner_username = username_cache[owner_tid_local]
            owner_title = f"{owner_username} (ID {owner_tid_local})" if owner_tid_local else "Не назначен"
            summary_text = (
                f"📊 Суммарно по {agg['count']} конфигам владельца {owner_title}:\n"
                f"   За сутки: ↑ {wireguard_stats.bytes_to_human(agg['day_sent'])} | ↓ {wireguard_stats.bytes_to_human(agg['day_recv'])}\n"
                f"   За неделю: ↑ {wireguard_stats.bytes_to_human(agg['week_sent'])} | ↓ {wireguard_stats.bytes_to_human(agg['week_recv'])}\n"
                f"   За месяц: ↑ {wireguard_stats.bytes_to_human(agg['month_sent'])} | ↓ {wireguard_stats.bytes_to_human(agg['month_recv'])}\n"
                f"   Всего: ↑ {wireguard_stats.bytes_to_human(agg['total_sent'])} | ↓ {wireguard_stats.bytes_to_human(agg['total_recv'])}"
            )
            await update.message.reply_text(summary_text, parse_mode="HTML")
        
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


    async def _buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        if await self._cancel_button_handler(update, context):
            await self._end_command(update, context)
            return True
        
        if (
            update.message is not None
            and update.message.text == keyboards.ButtonText.WIREGUARD_USER
        ):
            if update.effective_user is not None:
                await self._delete_message(update, context)
                await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
            return True
        
        return False
