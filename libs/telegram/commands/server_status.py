import asyncio
import os
from dataclasses import dataclass
from typing import Optional

from .base import *


@dataclass
class _MemoryUsage:
    total_mb: int
    used_mb: int
    percent: float
    available_mb: int | None = None


@dataclass
class _ServerMemoryStatus:
    ram: _MemoryUsage
    swap: _MemoryUsage


class ServerStatusCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        super().__init__(database)
        self.command_name = BotCommand.SERVER_STATUS

    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        if update.message is None:
            return

        loop = asyncio.get_running_loop()
        load = await loop.run_in_executor(None, self.__collect_loadavg)
        memory = await loop.run_in_executor(None, self.__collect_memory)
        uptime = await loop.run_in_executor(None, self.__collect_uptime)

        message_lines = ["🖥 <b>Состояние сервера</b>"]

        if load is not None:
            one, five, fifteen, perc_one, perc_five, perc_fifteen = load
            message_lines.append(
                "🧠 CPU load за 1/5/15 минут: "
                f"{one:.2f} / {five:.2f} / {fifteen:.2f} "
                f"({perc_one:.0f}% / {perc_five:.0f}% / {perc_fifteen:.0f}% от числа ядер)"
            )
        else:
            message_lines.append("🧠 CPU load: не удалось получить данные.")

        if memory is not None:
            message_lines.append(
                f"💾 RAM: {memory.ram.used_mb} / {memory.ram.total_mb} MiB ({memory.ram.percent:.0f}%)"
            )

            if memory.swap.total_mb > 0:
                message_lines.append(
                    f"💽 Swap: {memory.swap.used_mb} / {memory.swap.total_mb} MiB ({memory.swap.percent:.0f}%)"
                )
            else:
                message_lines.append("💽 Swap: не настроен")
        else:
            message_lines.append("💾 RAM: не удалось получить данные.")

        if uptime is not None:
            message_lines.append(f"⏱ Uptime: {uptime}")

        await update.message.reply_text("\n".join(message_lines), parse_mode="HTML")
        await self._end_command(update, context)

    def __collect_loadavg(self) -> Optional[tuple[float, float, float, float, float, float]]:
        getter = getattr(os, "getloadavg", None)
        one = five = fifteen = None

        if callable(getter):
            try:
                one, five, fifteen = getter()
            except OSError:
                one = five = fifteen = None

        # Фолбэк для Windows/окружений без getloadavg
        if one is None or five is None or fifteen is None:
            fallback = self.__read_proc_loadavg()
            if fallback is None:
                return None
            one, five, fifteen = fallback

        cores = os.cpu_count() or 1
        return (
            one,
            five,
            fifteen,
            (one / cores) * 100,
            (five / cores) * 100,
            (fifteen / cores) * 100,
        )

    def __read_proc_loadavg(self) -> Optional[tuple[float, float, float]]:
        """
        Простой фолбэк: читает /proc/loadavg, если доступно.
        """
        try:
            with open("/proc/loadavg", "r") as f:
                parts = f.read().split()
            if len(parts) >= 3:
                return float(parts[0]), float(parts[1]), float(parts[2])
        except (FileNotFoundError, PermissionError, ValueError):
            return None
        return None

    def __collect_memory(self) -> Optional[_ServerMemoryStatus]:
        meminfo_path = "/proc/meminfo"
        try:
            info: dict[str, int] = {}
            with open(meminfo_path, "r") as meminfo:
                for line in meminfo:
                    key, value, *_ = line.split()
                    info[key.rstrip(":")] = int(value)

            total_kb = info.get("MemTotal")
            if total_kb is None:
                return None

            free_kb = info.get("MemFree")
            buffers_kb = info.get("Buffers", 0)
            cached_kb = info.get("Cached", 0)
            reclaimable_kb = info.get("SReclaimable", 0)
            shmem_kb = info.get("Shmem", 0)
            available_kb = info.get("MemAvailable")

            # Формула ближе к htop: used = total - free - buffers - cache,
            # где cache считаем как Cached + SReclaimable - Shmem.
            cache_kb = max(cached_kb + reclaimable_kb - shmem_kb, 0)
            if free_kb is not None:
                used_kb = max(total_kb - free_kb - buffers_kb - cache_kb, 0)
            elif available_kb is not None:
                used_kb = max(total_kb - available_kb, 0)
            else:
                return None

            swap_total_kb = info.get("SwapTotal", 0)
            swap_free_kb = info.get("SwapFree", 0)
            swap_used_kb = max(swap_total_kb - swap_free_kb, 0)

            ram = _MemoryUsage(
                total_mb=int(total_kb / 1024),
                used_mb=int(used_kb / 1024),
                percent=(used_kb / total_kb) * 100 if total_kb else 0,
                available_mb=int(available_kb / 1024) if available_kb is not None else None,
            )
            swap = _MemoryUsage(
                total_mb=int(swap_total_kb / 1024),
                used_mb=int(swap_used_kb / 1024),
                percent=(swap_used_kb / swap_total_kb) * 100 if swap_total_kb else 0,
            )
            return _ServerMemoryStatus(ram=ram, swap=swap)
        except (FileNotFoundError, PermissionError, ValueError):
            return None

    def __collect_uptime(self) -> Optional[str]:
        try:
            with open("/proc/uptime", "r") as f:
                seconds = float(f.readline().split()[0])
        except (FileNotFoundError, PermissionError, ValueError):
            return None

        minutes, _ = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        parts = []
        if days:
            parts.append(f"{days}д")
        if hours:
            parts.append(f"{hours}ч")
        parts.append(f"{minutes}м")
        return " ".join(parts)
