import asyncio
import html
import logging
import math
from typing import Iterable, Optional

from telegram.error import TelegramError
from telegram.ext import CallbackContext

from libs.core.system_metrics import (
    CpuSnapshot,
    ProcessCpuSample,
    ProcessUsage,
    ServerMemoryStatus,
    calculate_cpu_percent,
    calculate_top_cpu_processes,
    collect_memory,
    collect_top_memory_processes,
    read_cpu_snapshot,
    read_process_cpu_samples,
)
from libs.telegram.types import TelegramId


logger = logging.getLogger(__name__)


class ServerHealthMonitor:
    _TOP_PROCESS_LIMIT = 5

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
        self._process_cpu_samples: dict[int, ProcessCpuSample] = read_process_cpu_samples()
        self._cpu_consecutive_hits = 0
        self._ram_consecutive_hits = 0
        self._cpu_alert_active = False
        self._ram_alert_active = False

    async def check(self, context: CallbackContext) -> None:
        if not self.admin_ids:
            return

        had_active_alert = self._cpu_alert_active or self._ram_alert_active

        (cpu_percent, cpu_top_processes), memory = await asyncio.gather(
            asyncio.to_thread(self.collect_cpu_status),
            asyncio.to_thread(collect_memory),
        )

        cpu_issue = self._update_cpu_state(cpu_percent)
        ram_issue = self._update_ram_state(memory)

        self._sync_cpu_alert_state(cpu_issue, cpu_percent)
        self._sync_ram_alert_state(ram_issue, memory)

        has_active_alert = self._cpu_alert_active or self._ram_alert_active
        if not cpu_issue and not ram_issue:
            if (
                had_active_alert
                and not has_active_alert
                and cpu_percent is not None
                and cpu_percent < self.cpu_threshold_percent
                and memory is not None
                and memory.ram.percent < self.ram_threshold_percent
            ):
                await self._send_message(
                    context,
                    self._build_recovery_text(cpu_percent=cpu_percent, memory=memory),
                )
            return

        ram_top_processes: list[ProcessUsage] = []
        if ram_issue and memory is not None:
            ram_top_processes = await asyncio.to_thread(
                collect_top_memory_processes,
                memory.ram.total_mb,
                self._TOP_PROCESS_LIMIT,
            )

        lines = ["⚠️ <b>Предупреждение о состоянии сервера</b>"]
        if cpu_issue and cpu_percent is not None:
            lines.append(
                "🧠 CPU: "
                f"{cpu_percent:.1f}% "
                f"(выше {self.cpu_threshold_percent:.0f}% уже {self._format_duration(self._cpu_consecutive_hits)})"
            )
            self._append_process_lines(lines, "Возможные виновники CPU", cpu_top_processes)

        if ram_issue and memory is not None:
            lines.append(
                "💾 RAM: "
                f"{memory.ram.used_mb} / {memory.ram.total_mb} MiB "
                f"({memory.ram.percent:.1f}%, порог {self.ram_threshold_percent:.0f}%) "
                f"уже {self._format_duration(self._ram_consecutive_hits)}"
            )
            self._append_process_lines(lines, "Возможные виновники RAM", ram_top_processes)
            if memory.swap.total_mb > 0:
                lines.append(
                    "💽 Swap: "
                    f"{memory.swap.used_mb} / {memory.swap.total_mb} MiB "
                    f"({memory.swap.percent:.1f}%)"
                )

        await self._send_message(context, "\n".join(lines))

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

    def collect_cpu_status(self) -> tuple[Optional[float], list[ProcessUsage]]:
        current_snapshot = read_cpu_snapshot()
        previous_snapshot = self._cpu_snapshot
        self._cpu_snapshot = current_snapshot

        current_process_samples = read_process_cpu_samples()
        previous_process_samples = self._process_cpu_samples
        self._process_cpu_samples = current_process_samples

        return (
            calculate_cpu_percent(previous_snapshot, current_snapshot),
            calculate_top_cpu_processes(
                previous_snapshot=previous_snapshot,
                current_snapshot=current_snapshot,
                previous_samples=previous_process_samples,
                current_samples=current_process_samples,
                limit=self._TOP_PROCESS_LIMIT,
            ),
        )

    def _sync_cpu_alert_state(self, cpu_issue: bool, cpu_percent: Optional[float]) -> None:
        if cpu_issue:
            self._cpu_alert_active = True
        elif cpu_percent is not None:
            self._cpu_alert_active = False

    def _sync_ram_alert_state(self, ram_issue: bool, memory: Optional[ServerMemoryStatus]) -> None:
        if ram_issue:
            self._ram_alert_active = True
        elif memory is not None:
            self._ram_alert_active = False

    def _format_duration(self, checks: int) -> str:
        seconds = checks * self.interval_seconds
        if seconds % 60 == 0:
            minutes = seconds // 60
            return f"{minutes} мин"
        return f"{seconds} сек"

    def _append_process_lines(
        self,
        lines: list[str],
        title: str,
        processes: list[ProcessUsage],
    ) -> None:
        if not processes:
            return

        total_percent = sum(process.percent for process in processes)
        lines.append(f"{html.escape(title)} ({total_percent:.1f}% суммарно):")
        for process in processes:
            process_name = html.escape(self._format_process_name(process))
            if process.used_mb is None:
                lines.append(
                    f"• {process_name} (<code>{process.pid}</code>) - {process.percent:.1f}%"
                )
            else:
                lines.append(
                    f"• {process_name} (<code>{process.pid}</code>) - "
                    f"{process.percent:.1f}% ({process.used_mb} MiB)"
                )

    def _format_process_name(self, process: ProcessUsage) -> str:
        name = process.name.strip() or str(process.pid)
        if len(name) > 32:
            return f"{name[:29]}..."
        return name

    def _build_recovery_text(
        self,
        cpu_percent: float,
        memory: ServerMemoryStatus,
    ) -> str:
        lines = ["✅ <b>Нагрузка нормализовалась</b>"]
        lines.append(
            f"🧠 CPU: {cpu_percent:.1f}% (ниже порога {self.cpu_threshold_percent:.0f}%)"
        )
        lines.append(
            "💾 RAM: "
            f"{memory.ram.used_mb} / {memory.ram.total_mb} MiB "
            f"({memory.ram.percent:.1f}%, ниже порога {self.ram_threshold_percent:.0f}%)"
        )
        if memory.swap.total_mb > 0:
            lines.append(
                f"💽 Swap: {memory.swap.used_mb} / {memory.swap.total_mb} MiB "
                f"({memory.swap.percent:.1f}%)"
            )
        return "\n".join(lines)

    async def _send_message(self, context: CallbackContext, text: str) -> None:
        for admin_id in self.admin_ids:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    parse_mode="HTML",
                )
            except TelegramError as exc:
                logger.error(
                    "Не удалось отправить системное уведомление админу %s: %s",
                    admin_id,
                    exc,
                )
