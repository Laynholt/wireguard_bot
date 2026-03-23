import asyncio
import logging
import math
from typing import Iterable, Optional

from telegram.error import TelegramError
from telegram.ext import CallbackContext

from libs.core.system_metrics import (
    CpuSnapshot,
    ServerMemoryStatus,
    calculate_cpu_percent,
    collect_memory,
    read_cpu_snapshot,
)
from libs.telegram.types import TelegramId


logger = logging.getLogger(__name__)


class ServerHealthMonitor:
    def __init__(
        self,
        admin_ids: Iterable[TelegramId],
        interval_seconds: int,
        cpu_threshold_percent: float,
        cpu_duration_minutes: int,
        ram_threshold_percent: float,
        ram_duration_minutes: int,
    ) -> None:
        self.admin_ids = tuple(dict.fromkeys(admin_ids))
        self.interval_seconds = max(interval_seconds, 1)
        self.cpu_threshold_percent = cpu_threshold_percent
        self.cpu_duration_checks = max(
            1,
            math.ceil(max(cpu_duration_minutes, 1) * 60 / self.interval_seconds),
        )
        self.ram_threshold_percent = ram_threshold_percent
        self.ram_duration_checks = max(
            1,
            math.ceil(max(ram_duration_minutes, 1) * 60 / self.interval_seconds),
        )

        self._cpu_snapshot: Optional[CpuSnapshot] = read_cpu_snapshot()
        self._cpu_consecutive_hits = 0
        self._ram_consecutive_hits = 0

    async def check(self, context: CallbackContext) -> None:
        if not self.admin_ids:
            return

        cpu_percent, memory = await asyncio.gather(
            asyncio.to_thread(self.collect_cpu_percent),
            asyncio.to_thread(collect_memory),
        )

        cpu_issue = self._update_cpu_state(cpu_percent)
        ram_issue = self._update_ram_state(memory)

        if not cpu_issue and not ram_issue:
            return

        lines = ["⚠️ <b>Предупреждение о состоянии сервера</b>"]
        if cpu_issue and cpu_percent is not None:
            lines.append(
                "🧠 CPU: "
                f"{cpu_percent:.1f}% "
                f"(выше {self.cpu_threshold_percent:.0f}% уже {self._format_duration(self._cpu_consecutive_hits)})"
            )

        if ram_issue and memory is not None:
            lines.append(
                "💾 RAM: "
                f"{memory.ram.used_mb} / {memory.ram.total_mb} MiB "
                f"({memory.ram.percent:.1f}%, порог {self.ram_threshold_percent:.0f}%) "
                f"уже {self._format_duration(self._ram_consecutive_hits)}"
            )
            if memory.swap.total_mb > 0:
                lines.append(
                    "💽 Swap: "
                    f"{memory.swap.used_mb} / {memory.swap.total_mb} MiB "
                    f"({memory.swap.percent:.1f}%)"
                )

        alert_text = "\n".join(lines)

        for admin_id in self.admin_ids:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=alert_text,
                    parse_mode="HTML",
                )
            except TelegramError as exc:
                logger.error(
                    "Не удалось отправить системное предупреждение админу %s: %s",
                    admin_id,
                    exc,
                )

    def _update_cpu_state(self, cpu_percent: Optional[float]) -> bool:
        if cpu_percent is None:
            self._cpu_consecutive_hits = 0
            return False

        if cpu_percent >= self.cpu_threshold_percent:
            self._cpu_consecutive_hits += 1
        else:
            self._cpu_consecutive_hits = 0

        return self._cpu_consecutive_hits >= self.cpu_duration_checks

    def _update_ram_state(self, memory: Optional[ServerMemoryStatus]) -> bool:
        if memory is None:
            self._ram_consecutive_hits = 0
            return False

        if memory.ram.percent >= self.ram_threshold_percent:
            self._ram_consecutive_hits += 1
        else:
            self._ram_consecutive_hits = 0

        return self._ram_consecutive_hits >= self.ram_duration_checks

    def collect_cpu_percent(self) -> Optional[float]:
        current_snapshot = read_cpu_snapshot()
        previous_snapshot = self._cpu_snapshot
        self._cpu_snapshot = current_snapshot

        return calculate_cpu_percent(previous_snapshot, current_snapshot)

    def _format_duration(self, checks: int) -> str:
        seconds = checks * self.interval_seconds
        if seconds % 60 == 0:
            minutes = seconds // 60
            return f"{minutes} мин"
        return f"{seconds} сек"
