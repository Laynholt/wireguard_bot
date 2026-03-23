from __future__ import annotations

import asyncio
import csv
import inspect
import os
import re
import tempfile

from dataclasses import dataclass
from datetime import datetime, date as dt_date
from typing import Iterable, Optional
from asyncio import Semaphore

from telegram import (
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import CallbackContext

from .base import *
from libs.telegram import messages
from libs.wireguard import stats as wireguard_stats
from libs.wireguard import wg_db
from libs.wireguard.user_control import sanitize_string


class GetWireguardStatsExportCommand(BaseCommand):
    _CTX_PREFIX = ContextDataKeys.STATS_EXPORT_PREFIX.value
    CTX_STAGE = f"{_CTX_PREFIX}stage"
    CTX_SCOPE = f"{_CTX_PREFIX}scope"
    CTX_TARGET_TELEGRAM_IDS = f"{_CTX_PREFIX}telegram_ids"
    CTX_TARGET_WIREGUARD_USERS = f"{_CTX_PREFIX}wireguard_users"

    RANGE_PATTERN = re.compile(
        r"\b(?P<key>from|to|start|end|date_from|date_to|с|по|от|до)\s*=\s*(?P<value>[^\s]+)",
        re.IGNORECASE
    )
    DATE_TOKEN_PATTERN = re.compile(r"\b\d{1,4}(?:-\d{1,2}){0,2}\b")

    class Scope:
        OWN = "own"
        TELEGRAM = "telegram"
        WIREGUARD = "wireguard"
        ALL = "all"

    @dataclass
    class RangeResolution:
        date_from: dt_date
        date_to: dt_date
        notes: list[str]
        has_explicit_input: bool

    def __init__(
        self,
        database: UserDatabase,
        semaphore: Semaphore,
    ) -> None:
        super().__init__(database)
        self.command_name = BotCommand.GET_STATS_EXPORT
        self.semaphore = semaphore
        self.keyboard = Keyboard(
            title=BotCommand.GET_STATS_EXPORT.pretty_text,
            reply_keyboard=ReplyKeyboardMarkup(
                (
                    (
                        KeyboardButton(
                            text=keyboards.ButtonText.TELEGRAM_USER.value.text,
                            request_users=KeyboardButtonRequestUsers(
                                request_id=0,
                                user_is_bot=False,
                                request_username=True,
                            )
                        ),
                        keyboards.ButtonText.WIREGUARD_USER.value.text,
                    ),
                    (
                        keyboards.ButtonText.OWN.value.text,
                        keyboards.ButtonText.ALL_USERS.value.text,
                    ),
                    (
                        keyboards.ButtonText.CANCEL.value.text,
                    ),
                ),
                one_time_keyboard=True
            )
        )
        self.keyboard.add_parent(keyboards.WIREGUARD_STATS_KEYBOARD)

    async def request_input(self, update: Update, context: CallbackContext):
        if update.message is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
            return

        if context.user_data is not None:
            context.user_data[ContextDataKeys.COMMAND] = self.command_name
            self.__reset_state(context)
            context.user_data[self.CTX_STAGE] = "select_scope"

        await update.message.reply_text(
            (
                "Выберите, по кому собрать CSV-файл статистики.\n\n"
                f"• {keyboards.ButtonText.OWN} — конфиги текущего пользователя\n"
                f"• {keyboards.ButtonText.TELEGRAM_USER} — конфиги выбранного Telegram-пользователя\n"
                f"• {keyboards.ButtonText.WIREGUARD_USER} — конкретные WireGuard-конфиги\n"
                f"• {keyboards.ButtonText.ALL_USERS} — все пользователи с данными\n\n"
                f"Для отмены нажмите {keyboards.ButtonText.CANCEL}."
            ),
            reply_markup=self.keyboard.reply_keyboard
        )

    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        if await self._buttons_handler(update, context):
            return None

        try:
            if update.message is None or context.user_data is None:
                return None

            stage = context.user_data.get(self.CTX_STAGE)

            if update.message.users_shared is not None:
                await self.__handle_shared_users(update, context)
                return None

            if stage == "await_wireguard_users":
                await self.__handle_wireguard_users_input(update, context)
                return None

            if stage == "await_range":
                await self.__handle_range_input(update, context)
                return None

            await update.message.reply_text(
                "Сначала выберите источник данных кнопками ниже."
            )
            return None
        finally:
            if context.user_data is not None and context.user_data.get(ContextDataKeys.COMMAND) != self.command_name:
                self.__reset_state(context)

    async def _buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        if await self._cancel_button_handler(update, context):
            self.__reset_state(context)
            await self._end_command(update, context)
            return True

        if update.message is None or context.user_data is None:
            return False

        if update.message.text == keyboards.ButtonText.OWN:
            await self._delete_message(update, context)
            context.user_data[self.CTX_SCOPE] = self.Scope.OWN
            context.user_data[self.CTX_STAGE] = "await_range"
            await self.__prompt_range(update)
            return True

        if update.message.text == keyboards.ButtonText.ALL_USERS:
            await self._delete_message(update, context)
            context.user_data[self.CTX_SCOPE] = self.Scope.ALL
            context.user_data[self.CTX_STAGE] = "await_range"
            await self.__prompt_range(update)
            return True

        if update.message.text == keyboards.ButtonText.WIREGUARD_USER:
            await self._delete_message(update, context)
            context.user_data[self.CTX_SCOPE] = self.Scope.WIREGUARD
            context.user_data[self.CTX_STAGE] = "await_wireguard_users"
            await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
            return True

        if update.message.text == keyboards.ButtonText.TELEGRAM_USER:
            await update.message.reply_text(
                "Используйте кнопку выбора Telegram-пользователя, чтобы бот получил корректный идентификатор."
            )
            return True

        return False

    async def __handle_shared_users(self, update: Update, context: CallbackContext) -> None:
        if update.message is None or context.user_data is None:
            return

        telegram_ids = [
            shared_user.user_id
            for shared_user in update.message.users_shared.users
        ]
        context.user_data[self.CTX_SCOPE] = self.Scope.TELEGRAM
        context.user_data[self.CTX_TARGET_TELEGRAM_IDS] = telegram_ids
        context.user_data[self.CTX_STAGE] = "await_range"
        await self.__prompt_range(update)

    async def __handle_wireguard_users_input(self, update: Update, context: CallbackContext) -> None:
        if update.message is None or update.message.text is None or context.user_data is None:
            return

        raw_entries = update.message.text.split()
        requested_users: list[str] = []
        for entry in raw_entries:
            cleaned = sanitize_string(entry)
            if cleaned:
                requested_users.append(cleaned)

        requested_users = list(dict.fromkeys(requested_users))
        if not requested_users:
            await update.message.reply_text(
                "Не удалось распознать ни одного имени. Введите один или несколько WireGuard-конфигов через пробел."
            )
            return

        stats_map = await asyncio.to_thread(wireguard_stats.load_stats_from_db)
        existing_users = [user for user in requested_users if user in stats_map]
        missing_users = [user for user in requested_users if user not in stats_map]

        if not existing_users:
            await update.message.reply_text(
                "Для указанных WireGuard-конфигов в базе нет сохранённой статистики."
            )
            return

        context.user_data[self.CTX_TARGET_WIREGUARD_USERS] = existing_users
        context.user_data[self.CTX_STAGE] = "await_range"

        if missing_users:
            await update.message.reply_text(
                "Часть конфигов пропущена, потому что для них нет данных в БД: "
                + ", ".join(f"<code>{user}</code>" for user in missing_users),
                parse_mode="HTML"
            )

        await self.__prompt_range(update)

    async def __handle_range_input(self, update: Update, context: CallbackContext) -> None:
        if update.message is None or context.user_data is None:
            return

        if not await self._check_database_state(update):
            self.__reset_state(context)
            await self._end_command(update, context)
            return

        stats_map = await asyncio.to_thread(wireguard_stats.load_stats_from_db)
        selected_users = self.__resolve_selected_users(
            stats_map=stats_map,
            effective_user_id=update.effective_user.id if update.effective_user is not None else None,
            context=context,
        )

        if not selected_users:
            await update.message.reply_text(
                "Для выбранного источника нет пользователей со статистикой в базе данных."
            )
            self.__reset_state(context)
            await self._end_command(update, context)
            return

        available_dates = self.__collect_available_dates(stats_map, selected_users)
        if not available_dates:
            await update.message.reply_text(
                "У выбранных пользователей нет дневной статистики, поэтому файл построить нельзя."
            )
            self.__reset_state(context)
            await self._end_command(update, context)
            return

        text = update.message.text or ""
        resolved_range = self.__resolve_range(text, available_dates)

        linked_users = self.database.get_all_linked_data()
        owner_tid_by_user = {user_name: tid for tid, user_name in linked_users}
        owner_ids = {
            owner_tid_by_user[user_name]
            for user_name in selected_users
            if user_name in owner_tid_by_user
        }
        owner_usernames = await telegram_utils.get_usernames_in_bulk(
            owner_ids, context, self.semaphore
        )
        created_at_by_user = wg_db.get_users_created_at(selected_users)

        csv_rows = self.__build_csv_rows(
            selected_users=selected_users,
            stats_map=stats_map,
            owner_tid_by_user=owner_tid_by_user,
            owner_usernames=owner_usernames,
            created_at_by_user=created_at_by_user,
            date_from=resolved_range.date_from,
            date_to=resolved_range.date_to,
        )

        if not csv_rows:
            await update.message.reply_text(
                "В указанном диапазоне нет данных для выбранных пользователей."
            )
            self.__reset_state(context)
            await self._end_command(update, context)
            return

        csv_path = self.__write_csv_file(csv_rows)
        try:
            caption_lines = [
                "🗂 CSV-файл статистики готов.",
                f"Пользователей: {len(selected_users)}",
                f"Строк: {len(csv_rows)}",
                f"Период: {resolved_range.date_from.isoformat()} .. {resolved_range.date_to.isoformat()}",
            ]
            caption_lines.extend(resolved_range.notes[:3])

            with open(csv_path, "rb") as report_file:
                await update.message.reply_document(
                    document=report_file,
                    filename=os.path.basename(csv_path),
                    caption="\n".join(caption_lines),
                )
        finally:
            try:
                os.remove(csv_path)
            except OSError:
                pass

        self.__reset_state(context)
        await self._end_command(update, context)

    async def __prompt_range(self, update: Update) -> None:
        if update.message is None:
            return

        await update.message.reply_text(
            (
                "Теперь укажите диапазон дат для файла.\n\n"
                "Поддерживаются варианты:\n"
                "• <code>all</code> или <code>*</code> — все даты\n"
                "• <code>from=2026-03-01 to=2026-03-20</code>\n"
                "• <code>from=03-01</code>\n"
                "• <code>to=20</code>\n"
                "• <code>2026-03-01 2026-03-20</code>\n\n"
                "Если одна из границ невалидна или выходит за доступный диапазон, "
                "она будет автоматически заменена на ближайшую корректную."
            ),
            parse_mode="HTML"
        )

    def __resolve_selected_users(
        self,
        stats_map: dict[str, wireguard_stats.WgPeerData],
        effective_user_id: Optional[int],
        context: CallbackContext,
    ) -> list[str]:
        if context.user_data is None:
            return []

        scope = context.user_data.get(self.CTX_SCOPE)
        if scope == self.Scope.ALL:
            return sorted(stats_map.keys())

        if scope == self.Scope.OWN:
            if effective_user_id is None:
                return []
            linked_users = self.database.get_users_by_telegram_id(effective_user_id)
            return [user for user in linked_users if user in stats_map]

        if scope == self.Scope.TELEGRAM:
            telegram_ids = context.user_data.get(self.CTX_TARGET_TELEGRAM_IDS, [])
            result: list[str] = []
            for telegram_id in telegram_ids:
                result.extend(self.database.get_users_by_telegram_id(telegram_id))
            result = list(dict.fromkeys(result))
            return [user for user in result if user in stats_map]

        if scope == self.Scope.WIREGUARD:
            return [
                user
                for user in context.user_data.get(self.CTX_TARGET_WIREGUARD_USERS, [])
                if user in stats_map
            ]

        return []

    def __collect_available_dates(
        self,
        stats_map: dict[str, wireguard_stats.WgPeerData],
        selected_users: Iterable[str],
    ) -> list[dt_date]:
        available_dates: set[dt_date] = set()
        for user_name in selected_users:
            user_data = stats_map.get(user_name)
            if user_data is None:
                continue
            for day_key in user_data.periods.daily.keys():
                try:
                    available_dates.add(dt_date.fromisoformat(day_key))
                except ValueError:
                    continue
        return sorted(available_dates)

    def __resolve_range(self, text: str, available_dates: list[dt_date]) -> RangeResolution:
        min_date = available_dates[0]
        max_date = available_dates[-1]
        normalized = (text or "").strip()
        notes: list[str] = []

        if normalized.lower() in {"", "all", "*", "-", "все", "всё"}:
            return self.RangeResolution(
                date_from=min_date,
                date_to=max_date,
                notes=[],
                has_explicit_input=False,
            )

        raw_from: Optional[str] = None
        raw_to: Optional[str] = None
        for match in self.RANGE_PATTERN.finditer(normalized):
            key = match.group("key").lower()
            value = match.group("value").strip()
            if key in {"from", "start", "date_from", "с", "от"}:
                raw_from = value
            else:
                raw_to = value

        if raw_from is None and raw_to is None:
            tokens = self.DATE_TOKEN_PATTERN.findall(normalized)
            if len(tokens) >= 2:
                raw_from = tokens[0]
                raw_to = tokens[1]
            elif len(tokens) == 1:
                raw_from = tokens[0]
                raw_to = tokens[0]
            else:
                notes.append("Диапазон не распознан, использованы все доступные даты.")
                return self.RangeResolution(
                    date_from=min_date,
                    date_to=max_date,
                    notes=notes,
                    has_explicit_input=True,
                )

        parsed_from = self.__parse_flexible_date(raw_from) if raw_from is not None else None
        parsed_to = self.__parse_flexible_date(raw_to) if raw_to is not None else None

        effective_from = self.__normalize_boundary(
            parsed_value=parsed_from,
            fallback=min_date,
            minimum=min_date,
            maximum=max_date,
            raw_value=raw_from,
            label="from",
            notes=notes,
        )
        effective_to = self.__normalize_boundary(
            parsed_value=parsed_to,
            fallback=max_date,
            minimum=min_date,
            maximum=max_date,
            raw_value=raw_to,
            label="to",
            notes=notes,
        )

        if effective_from > effective_to:
            effective_from, effective_to = effective_to, effective_from
            notes.append("Границы диапазона были переставлены местами.")

        return self.RangeResolution(
            date_from=effective_from,
            date_to=effective_to,
            notes=notes,
            has_explicit_input=True,
        )

    def __normalize_boundary(
        self,
        parsed_value: Optional[dt_date],
        fallback: dt_date,
        minimum: dt_date,
        maximum: dt_date,
        raw_value: Optional[str],
        label: str,
        notes: list[str],
    ) -> dt_date:
        if raw_value is None:
            return fallback

        if parsed_value is None:
            notes.append(f"Граница {label} скорректирована до {fallback.isoformat()}.")
            return fallback

        if parsed_value < minimum:
            notes.append(f"Граница {label} скорректирована до {minimum.isoformat()}.")
            return minimum

        if parsed_value > maximum:
            notes.append(f"Граница {label} скорректирована до {maximum.isoformat()}.")
            return maximum

        return parsed_value

    def __parse_flexible_date(self, raw: Optional[str]) -> Optional[dt_date]:
        if raw is None:
            return None

        value = raw.strip()
        if not value:
            return None

        m_full = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
        if m_full:
            try:
                return dt_date(int(m_full.group(1)), int(m_full.group(2)), int(m_full.group(3)))
            except ValueError:
                return None

        m_month_day = re.fullmatch(r"(\d{1,2})-(\d{1,2})", value)
        if m_month_day:
            now = datetime.now().date()
            try:
                return dt_date(now.year, int(m_month_day.group(1)), int(m_month_day.group(2)))
            except ValueError:
                return None

        m_day = re.fullmatch(r"(\d{1,2})", value)
        if m_day:
            now = datetime.now().date()
            try:
                return dt_date(now.year, now.month, int(m_day.group(1)))
            except ValueError:
                return None

        return None

    def __build_csv_rows(
        self,
        selected_users: Iterable[str],
        stats_map: dict[str, wireguard_stats.WgPeerData],
        owner_tid_by_user: dict[str, int],
        owner_usernames: dict[int, Optional[str]],
        created_at_by_user: dict[str, Optional[str]],
        date_from: dt_date,
        date_to: dt_date,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []

        for user_name in sorted(selected_users):
            user_data = stats_map.get(user_name)
            if user_data is None:
                continue

            owner_tid = owner_tid_by_user.get(user_name)
            current_total_sent_bytes = wireguard_stats.human_to_bytes(user_data.transfer_sent)
            current_total_received_bytes = wireguard_stats.human_to_bytes(user_data.transfer_received)

            for day_key, day_stat in sorted(user_data.periods.daily.items()):
                try:
                    day_date = dt_date.fromisoformat(day_key)
                except ValueError:
                    continue

                if not (date_from <= day_date <= date_to):
                    continue

                day_total_bytes = day_stat.sent_bytes + day_stat.received_bytes
                rows.append(
                    {
                        "date": day_date.isoformat(),
                        "wireguard_user": user_name,
                        "telegram_id": owner_tid or "",
                        "telegram_username": owner_usernames.get(owner_tid) or "",
                        "created_at": created_at_by_user.get(user_name) or "",
                        "allowed_ip": user_data.allowed_ips or "",
                        "day_sent_bytes": day_stat.sent_bytes,
                        "day_received_bytes": day_stat.received_bytes,
                        "day_total_bytes": day_total_bytes,
                        "day_sent_human": wireguard_stats.bytes_to_human(day_stat.sent_bytes),
                        "day_received_human": wireguard_stats.bytes_to_human(day_stat.received_bytes),
                        "day_total_human": wireguard_stats.bytes_to_human(day_total_bytes),
                        "current_total_sent_bytes": current_total_sent_bytes,
                        "current_total_received_bytes": current_total_received_bytes,
                        "current_total_bytes": current_total_sent_bytes + current_total_received_bytes,
                        "current_total_sent_human": user_data.transfer_sent or "0 B",
                        "current_total_received_human": user_data.transfer_received or "0 B",
                    }
                )

        rows.sort(key=lambda row: (str(row["date"]), str(row["wireguard_user"])))
        return rows

    def __write_csv_file(self, rows: list[dict[str, object]]) -> str:
        fd, csv_path = tempfile.mkstemp(prefix="wireguard_stats_", suffix=".csv")
        os.close(fd)

        fieldnames = [
            "date",
            "wireguard_user",
            "telegram_id",
            "telegram_username",
            "created_at",
            "allowed_ip",
            "day_sent_bytes",
            "day_received_bytes",
            "day_total_bytes",
            "day_sent_human",
            "day_received_human",
            "day_total_human",
            "current_total_sent_bytes",
            "current_total_received_bytes",
            "current_total_bytes",
            "current_total_sent_human",
            "current_total_received_human",
        ]

        with open(csv_path, "w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return csv_path

    def __reset_state(self, context: CallbackContext) -> None:
        if context.user_data is None:
            return

        context.user_data.pop(self.CTX_STAGE, None)
        context.user_data.pop(self.CTX_SCOPE, None)
        context.user_data.pop(self.CTX_TARGET_TELEGRAM_IDS, None)
        context.user_data.pop(self.CTX_TARGET_WIREGUARD_USERS, None)
