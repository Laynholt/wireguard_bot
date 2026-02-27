from __future__ import annotations
import asyncio
from .base import *
from libs.wireguard import stats as wireguard_stats
from libs.wireguard import wg_db
from datetime import datetime

import re
from enum import Enum
from asyncio import Semaphore
from dataclasses import dataclass, field

class GetAllWireguardUsersStatsCommand(BaseCommand):
    class SortSequence(Enum):
        ASCENDING = 1
        DESCENDING = 2

    class Metric(Enum):
        TOTAL = "total"
        DAILY = "daily"
        WEEKLY = "weekly"
        MONTHLY = "monthly"
        
    @dataclass
    class Params:
        """Результат парсинга строки с параметрами."""
        sort: "GetAllWireguardUsersStatsCommand.SortSequence" = field(
            default_factory=lambda: GetAllWireguardUsersStatsCommand.SortSequence.DESCENDING
        )
        metric: "GetAllWireguardUsersStatsCommand.Metric" = field(
            default_factory=lambda: GetAllWireguardUsersStatsCommand.Metric.TOTAL
        )
        head: int = 0
        tail: int = 0
        show_totals: bool = False


    def __init__(
        self,
        database: UserDatabase,
        semaphore: Semaphore,
        wireguard_config_path: str,
    ) -> None:
        super().__init__(
            database
        )
        self.command_name = BotCommand.GET_ALL_STATS
        self.semaphore = semaphore
        self.wireguard_config_path = wireguard_config_path
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Позволяет задать ключи сортировки и вывода для 
        дальнейшей отправки статистики по конфигам Wireguard.
        """
        if update.message is not None:
            await update.message.reply_text(
        """
Шпаргалка:
Формат: <em>sort=[a|d] metric=[t|d|w|m] head=[N] tail=[M] sum=[1|0]</em>

• <b>sort</b>: a/asc/воз/1 → ↑, d/desc/убыв/2 → ↓ (по умолчанию ↓)
• <b>metric</b>: t=total (default), d=day, w=week, m=month
• <b>head=N</b> — первые N, <b>tail=M</b> — последние M (N,M ≥ 0)
• <b>sum=1</b> — показать сводку (сутки/неделя/месяц/всё)

Параметры в любом порядке, можно пропускать
• head=0 tail=0 → список пуст (только sum, если включён)
• Если head+tail >= len → выводятся все
• Неверные head/tail → выводятся все элементы

Примеры:
• <code>sort=asc head=5</code>
• <code>tail=4</code>
• <code>head=3 tail=2</code>
• <code>head=0 sum=1</code>
• <code>head=5 sum=1</code>
• <code>head=5 metric=d sum=1</code>

        """,
        parse_mode="HTML"
        )
        if context.user_data is not None: 
            context.user_data[ContextDataKeys.COMMAND] = self.command_name
        
    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Команда для администраторов.
        Выводит статистику для всех конфигов WireGuard, включая информацию о владельце
        (Telegram ID и username). Если владелец не привязан, выводит соответствующую пометку.
        Использует переданные ключи сортировки и вывода из request_input.
        """
        try:
            if update.message is None:
                if (curr_frame := inspect.currentframe()):
                    logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
                return
            
            keys = update.message.text
            parsed_keys = self.Params()
            if keys is not None and keys.strip():
                parsed_keys = self.__parse_params(
                    s=keys.strip(),
                    default_sort=self.SortSequence.DESCENDING,
                    default_metric=self.Metric.TOTAL,
                    default_head=-1,
                    default_tail=-1
                )
            
            # Сначала получаем всю статистику (сортировку настроим вручную по metric)
            all_wireguard_stats = await asyncio.to_thread(
                wireguard_stats.accumulate_wireguard_stats,
                conf_file_path=self.wireguard_config_path,
                sort_by=wireguard_stats.SortBy.TRANSFER_SENT,
                reverse_sort=True
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
            inactive_usernames = await asyncio.to_thread(wireguard.get_inactive_usernames)

            # Подготовим сортировку по выбранному metric
            def _metric_value(user_data: wireguard_stats.WgPeerData) -> int:
                if parsed_keys.metric == self.Metric.TOTAL:
                    return (
                        wireguard_stats.human_to_bytes(user_data.transfer_sent)
                        + wireguard_stats.human_to_bytes(user_data.transfer_received)
                    )
                if parsed_keys.metric == self.Metric.DAILY:
                    stat = wireguard_stats.get_period_usage(user_data, wireguard_stats.Period.DAILY)
                    return stat.sent_bytes + stat.received_bytes
                if parsed_keys.metric == self.Metric.WEEKLY:
                    stat = wireguard_stats.get_period_usage(user_data, wireguard_stats.Period.WEEKLY)
                    return stat.sent_bytes + stat.received_bytes
                if parsed_keys.metric == self.Metric.MONTHLY:
                    stat = wireguard_stats.get_period_usage(user_data, wireguard_stats.Period.MONTHLY)
                    return stat.sent_bytes + stat.received_bytes
                return 0

            items_sorted = sorted(
                all_wireguard_stats.items(),
                key=lambda kv: _metric_value(kv[1]),
                reverse=parsed_keys.sort == self.SortSequence.DESCENDING
            )
            created_at_by_user = wg_db.get_users_created_at(all_wireguard_stats.keys())
            
            indexes = self.__make_index_range(
                len(all_wireguard_stats),
                head=parsed_keys.head,
                tail=parsed_keys.tail
            )

            if parsed_keys.show_totals:
                total_day_sent = total_day_recv = 0
                total_week_sent = total_week_recv = 0
                total_month_sent = total_month_recv = 0
                total_sent = total_recv = 0
                for _, user_data in all_wireguard_stats.items():
                    day_stat_all = wireguard_stats.get_period_usage(user_data, wireguard_stats.Period.DAILY)
                    week_stat_all = wireguard_stats.get_period_usage(user_data, wireguard_stats.Period.WEEKLY)
                    month_stat_all = wireguard_stats.get_period_usage(user_data, wireguard_stats.Period.MONTHLY)
                    total_day_sent += day_stat_all.sent_bytes
                    total_day_recv += day_stat_all.received_bytes
                    total_week_sent += week_stat_all.sent_bytes
                    total_week_recv += week_stat_all.received_bytes
                    total_month_sent += month_stat_all.sent_bytes
                    total_month_recv += month_stat_all.received_bytes
                    total_sent += wireguard_stats.human_to_bytes(user_data.transfer_sent)
                    total_recv += wireguard_stats.human_to_bytes(user_data.transfer_received)

                totals_text = (
                    "📊 <b>Суммарно по всем конфигаx:</b>\n"
                    f"   За сутки: ↑ {wireguard_stats.bytes_to_human(total_day_sent)} | ↓ {wireguard_stats.bytes_to_human(total_day_recv)}\n"
                    f"   За неделю: ↑ {wireguard_stats.bytes_to_human(total_week_sent)} | ↓ {wireguard_stats.bytes_to_human(total_week_recv)}\n"
                    f"   За месяц: ↑ {wireguard_stats.bytes_to_human(total_month_sent)} | ↓ {wireguard_stats.bytes_to_human(total_month_recv)}\n"
                    f"   Всего: ↑ {wireguard_stats.bytes_to_human(total_sent)} | ↓ {wireguard_stats.bytes_to_human(total_recv)}"
                )
                await update.message.reply_text(totals_text, parse_mode="HTML")

            for i, (wg_user, user_data) in enumerate(items_sorted, start=1):       
                if not indexes:
                    # Если индексы пусты (head=0 и tail=0), выводим только сводку sum (если была) и выходим
                    logger.info("head=0 и tail=0 → список конфигов не выводится.")
                    break
                if i not in indexes:
                    continue
            
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
                created_at_human = "N/A"
                created_raw = created_at_by_user.get(wg_user)
                if created_raw:
                    try:
                        created_at_human = datetime.fromisoformat(created_raw).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        created_at_human = created_raw

                lines.append(
                    f"\n<b>{i}]</b> <b>🌐 Конфиг:</b> <i>{wg_user}</i> "
                    f"{'🔴 <b>[Неактивен]</b>' if wg_user in inactive_usernames else '🟢 <b>[Активен]</b>'}\n"
                    f"   {owner_part}\n"
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

            tid = -1
            if update.effective_user is not None:
                tid = update.effective_user.id
            
            logger.info(f"Отправляю статистику по всем конфигам Wireguard -> Tid [{tid}].")
            
            # Разбиваем на батчи по указанному размеру
            batched_lines = telegram_utils.build_batched_lines(
                lines=lines,
                max_items_per_batch=5,
            )
            
            await telegram_utils.send_batched_messages(
                update=update,
                batched_lines=batched_lines,
                parse_mode="HTML",
                groups_before_delay=2,
                delay_between_groups=0.5
            )

        finally:
            await self._end_command(update, context)
        
        
    def __map_sort(self, raw: Optional[str], default: SortSequence) -> SortSequence:
        """
        Преобразует строковое/числовое представление sort в SortSequence.
        Поддерживает: 'a', 'asc', 'ascending', 'воз', '1' -> ASCENDING
                    'd', 'desc', 'descending', 'убыв', '2' -> DESCENDING
        В противном случае возвращает default.
        """
        if raw is None:
            return default

        v = raw.strip().lower()
        if v in {"a", "asc", "ascending", "воз"}:
            return self.SortSequence.ASCENDING
        if v in {"d", "desc", "descending", "убыв"}:
            return self.SortSequence.DESCENDING

        # Попробовать распарсить как число (1/2)
        try:
            n = int(v)
            return self.SortSequence(n)
        except Exception:
            return default

    def __map_metric(self, raw: Optional[str], default: Metric) -> Metric:
        """
        Преобразует строковое представление metric в Metric.
        Поддерживает: total/t, day/d/daily, week/w/weekly, month/m/monthly.
        """
        if raw is None:
            return default
        v = raw.strip().lower()
        if v in {"t", "total"}:
            return self.Metric.TOTAL
        if v in {"d", "day", "daily"}:
            return self.Metric.DAILY
        if v in {"w", "week", "weekly"}:
            return self.Metric.WEEKLY
        if v in {"m", "month", "monthly"}:
            return self.Metric.MONTHLY
        return default
            
    def __parse_params(
        self,
        s: str,
        default_sort: SortSequence = SortSequence.DESCENDING,
        default_metric: Metric = Metric.TOTAL,
        default_head: int = -1,
        default_tail: int = -1,
) -> Params:
        """
        Разбирает строку вида 'sort=sortType head=N tail=M'.
        Если параметр не указан или некорректен — используется значение по умолчанию.
        """
        if not isinstance(s, str):
            s = str(s)

        # поиск sort
        m_sort = re.compile(r"\bsort=([^\s]+)\b").search(s)
        sort_raw  = m_sort.group(1) if m_sort else None
        sort_value = self.__map_sort(sort_raw, default_sort)

        # поиск metric
        m_metric = re.compile(r"\bmetric=([^\s]+)\b").search(s)
        metric_raw = m_metric.group(1) if m_metric else None
        metric_value = self.__map_metric(metric_raw, default_metric)

        # поиск head и tail (поддерживаем и отрицательные числа)
        m_head = re.compile(r"\bhead=([+-]?\d+)\b").search(s)
        m_tail = re.compile(r"\btail=([+-]?\d+)\b").search(s)

        if m_head:
            try:
                head_value = int(m_head.group(1))
                if head_value < 0:
                    head_value = -1  # сигнал "некорректно" -> показать все
            except ValueError:
                head_value = -1
        else:
            head_value = default_head

        if m_tail:
            try:
                tail_value = int(m_tail.group(1))
                if tail_value < 0:
                    tail_value = -1  # сигнал "некорректно" -> показать все
            except ValueError:
                tail_value = -1
        else:
            tail_value = default_tail

        # поиск флага sum/summary
        m_totals = re.compile(r"\b(sum|summary)=([^\s]+)\b", re.IGNORECASE).search(s)
        show_totals = False
        if m_totals:
            v = m_totals.group(2).lower()
            show_totals = v in {"1", "true", "yes", "y", "on", "да", "истина"}

        return self.Params(
            sort=sort_value,
            metric=metric_value,
            head=head_value,
            tail=tail_value,
            show_totals=show_totals
        )
    

    def __make_index_range(self, elements_size: int, head: int = 0, tail: int = 0) -> List[int]:
        """
        Формирует список индексов по правилам:
        - первые `head` элементов -> индексы 1 .. head
        - последние `tail` элементов -> индексы len(elements)-tail + 1 .. len(elements)

        Предполагается, что `head` и `tail` — целые числа (int).
        Поведение при краевых ситуациях:
        - Если elements_size 0 -> вернём [].
        - Если head < 0 или tail < 0 -> некорректный ввод -> вернём все индексы.
        - Если head == 0 and tail == 0 -> вернём [] (ничего не выводим).
        - Если head + tail >= len(elements) -> диапазоны пересекаются или покрывают всё -> вернём все индексы.
        Возвращаемые индексы — 1-based.
        """
        if elements_size == 0:
            return []

        # Оба равны 0 -> ничего не показываем
        if head == 0 and tail == 0:
            return []

        # Если передали отрицательные значения — считаем ввод некорректным -> вернуть все индексы
        if head < 0 or tail < 0:
            return list(range(1, elements_size + 1))

        # Ограничиваем head/tail верхним пределом n (безопасно)
        if head > elements_size:
            head = elements_size
        if tail > elements_size:
            tail = elements_size

        # Если перекрываются или покрывают весь массив -> вернуть все
        if head + tail >= elements_size:
            return list(range(1, elements_size + 1))

        indices: List[int] = []
        if head > 0:
            indices.extend(range(1, head + 1))
        if tail > 0:
            indices.extend(range(elements_size - tail + 1, elements_size + 1))
        return indices
