from __future__ import annotations
from .base import *
from libs.wireguard import stats as wireguard_stats

import re
from enum import Enum
from asyncio import Semaphore
from dataclasses import dataclass, field

class GetAllWireguardUsersStatsCommand(BaseCommand):
    class SortSequence(Enum):
        ASCENDING = 1
        DESCENDING = 2
        
    @dataclass
    class Params:
        """Результат парсинга строки с параметрами."""
        sort: "GetAllWireguardUsersStatsCommand.SortSequence" = field(
            default_factory=lambda: GetAllWireguardUsersStatsCommand.SortSequence.DESCENDING
        )
        head: int = 0
        tail: int = 0


    def __init__(
        self,
        database: UserDatabase,
        semaphore: Semaphore,
        wireguard_config_path: str,
        wireguard_log_path: str
    ) -> None:
        super().__init__(
            database
        )
        self.command_name = BotCommand.GET_ALL_STATS
        self.semaphore = semaphore
        self.wireguard_config_path = wireguard_config_path
        self.wireguard_log_path = wireguard_log_path
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Позволяет задать ключи сортировки и вывода для 
        дальнейшей отправки статистики по конфигам Wireguard.
        """
        if update.message is not None:
            await update.message.reply_text(
        """
ℹ️ Формат ввода (в одну строку):
sort=<тип> head=<N> tail=<M>

Параметры:
• sort — порядок сортировки. Допустимые значения (без учёта регистра):
— asc, ascending, 1  → ASCENDING
— desc, descending, 2 → DESCENDING
По умолчанию: DESCENDING.

• head — целое число (≥ 0). Берём первые N элементов. По умолчанию: 0 (не задано).

• tail — целое число (≥ 0). Берём последние M элементов. По умолчанию: 0 (не задано).

Правила:
• Параметры могут идти в любом порядке и быть опущены.
• Если указаны оба head и tail — учитываются оба (например: head=3 tail=2).
• Если head == 0 и tail == 0 → возвращаются ВСЕ элементы.
• Если head + tail >= длина_списка (диапазоны перекрываются или покрывают весь список) → возвращаются ВСЕ элементы.
• При некорректных значениях (отрицательные числа, нецелые, неверный формат) → возвращаются ВСЕ элементы.

Примеры:
• sort=asc head=5        — первые 5 элементов, сортировка ASCENDING
• tail=4 sort=desc       — последние 4 элемента, сортировка DESCENDING
• head=3 tail=2         — первые 3 и последние 2 элемента
• (пустая строка)       — все элементы (по умолчанию)
• head=7 tail=5 (len=10) — перекрытие → все элементы
        """
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
                    default_head=0,
                    default_tail=0
                )
            
            # Сначала получаем всю статистику
            all_wireguard_stats = wireguard_stats.accumulate_wireguard_stats(
                conf_file_path=self.wireguard_config_path,
                json_file_path=self.wireguard_log_path,
                sort_by=wireguard_stats.SortBy.TRANSFER_SENT,
                reverse_sort=parsed_keys.sort == self.SortSequence.DESCENDING
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
            
            indexes = self.__make_index_range(
                len(all_wireguard_stats.items()),
                head=parsed_keys.head,
                tail=parsed_keys.tail
            )
            for i, (wg_user, user_data) in enumerate(all_wireguard_stats.items(), start=1):       
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

                lines.append(
                    f"\n<b>{i}]</b> <b>🌐 Конфиг:</b> <i>{wg_user}</i> "
                    f"{'🔴 <b>[Неактивен]</b>' if wg_user in inactive_usernames else '🟢 <b>[Активен]</b>'}\n"
                    f"   {owner_part}\n"
                    f"   📡 IP: {user_data.allowed_ips}\n"
                    f"   📤 Отправлено: {user_data.transfer_received if user_data.transfer_received else 'N/A'}\n"
                    f"   📥 Получено: {user_data.transfer_sent if user_data.transfer_sent else 'N/A'}\n"
                    f"   ⏱️ Последнее рукопожатие: {user_data.latest_handshake if user_data.latest_handshake else 'N/A'}\n"
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
        
        
    def __map_sort(self, raw: Optional[str], default: SortSequence) -> SortSequence:
        """
        Преобразует строковое/числовое представление sort в SortSequence.
        Поддерживает: 'asc', 'ascending', '1' -> ASCENDING
                    'desc', 'descending', '2' -> DESCENDING
        В противном случае возвращает default.
        """
        if raw is None:
            return default

        v = raw.strip().lower()
        if v in {"asc", "ascending"}:
            return self.SortSequence.ASCENDING
        if v in {"desc", "descending"}:
            return self.SortSequence.DESCENDING

        # Попробовать распарсить как число (1/2)
        try:
            n = int(v)
            return self.SortSequence(n)
        except Exception:
            return default
            
    def __parse_params(
        self,
        s: str,
        default_sort: SortSequence = SortSequence.DESCENDING,
        default_head: int = 0,
        default_tail: int = 0,
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

        # поиск head и tail (поддерживаем и отрицательные числа)
        m_head = re.compile(r"\bhead=([+-]?\d+)\b").search(s)
        m_tail = re.compile(r"\btail=([+-]?\d+)\b").search(s)

        if m_head:
            try:
                head_value = int(m_head.group(1))
                if head_value < 0:
                    head_value = default_head
            except ValueError:
                head_value = default_head
        else:
            head_value = default_head

        if m_tail:
            try:
                tail_value = int(m_tail.group(1))
                if tail_value < 0:
                    tail_value = default_tail
            except ValueError:
                tail_value = default_tail
        else:
            tail_value = default_tail

        return self.Params(sort=sort_value, head=head_value, tail=tail_value)
    

    def __make_index_range(self, elements_size: int, head: int = 0, tail: int = 0) -> List[int]:
        """
        Формирует список индексов по правилам:
        - первые `head` элементов -> индексы 1 .. head
        - последние `tail` элементов -> индексы len(elements)-tail + 1 .. len(elements)

        Предполагается, что `head` и `tail` — целые числа (int).
        Поведение при краевых ситуациях:
        - Если elements_size 0 -> вернём [].
        - Если head < 0 или tail < 0 -> некорректный ввод -> вернём все индексы.
        - Если head == 0 and tail == 0 -> вернём все индексы.
        - Если head + tail >= len(elements) -> диапазоны пересекаются или покрывают всё -> вернём все индексы.
        Возвращаемые индексы — 1-based.
        """
        if elements_size == 0:
            return []

        # Оба равны 0 -> вернуть все
        if head == 0 and tail == 0:
            return list(range(1, elements_size + 1))

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