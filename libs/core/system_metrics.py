import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class MemoryUsage:
    total_mb: int
    used_mb: int
    percent: float
    available_mb: int | None = None


@dataclass
class ServerMemoryStatus:
    ram: MemoryUsage
    swap: MemoryUsage


@dataclass
class CpuSnapshot:
    idle: int
    total: int


def collect_loadavg() -> Optional[tuple[float, float, float, float, float, float]]:
    getter = getattr(os, "getloadavg", None)
    one = five = fifteen = None

    if callable(getter):
        try:
            one, five, fifteen = getter()
        except OSError:
            one = five = fifteen = None

    if one is None or five is None or fifteen is None:
        fallback = read_proc_loadavg()
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


def read_proc_loadavg() -> Optional[tuple[float, float, float]]:
    try:
        with open("/proc/loadavg", "r") as f:
            parts = f.read().split()
        if len(parts) >= 3:
            return float(parts[0]), float(parts[1]), float(parts[2])
    except (FileNotFoundError, PermissionError, ValueError):
        return None
    return None


def collect_memory() -> Optional[ServerMemoryStatus]:
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

        ram = MemoryUsage(
            total_mb=int(total_kb / 1024),
            used_mb=int(used_kb / 1024),
            percent=(used_kb / total_kb) * 100 if total_kb else 0,
            available_mb=int(available_kb / 1024) if available_kb is not None else None,
        )
        swap = MemoryUsage(
            total_mb=int(swap_total_kb / 1024),
            used_mb=int(swap_used_kb / 1024),
            percent=(swap_used_kb / swap_total_kb) * 100 if swap_total_kb else 0,
        )
        return ServerMemoryStatus(ram=ram, swap=swap)
    except (FileNotFoundError, PermissionError, ValueError):
        return None


def collect_uptime() -> Optional[str]:
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


def read_cpu_snapshot() -> Optional[CpuSnapshot]:
    try:
        with open("/proc/stat", "r") as stat_file:
            cpu_line = stat_file.readline().split()
    except (FileNotFoundError, PermissionError, ValueError):
        return None

    if len(cpu_line) < 5 or cpu_line[0] != "cpu":
        return None

    try:
        values = [int(value) for value in cpu_line[1:]]
    except ValueError:
        return None

    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    return CpuSnapshot(idle=idle, total=total)


def calculate_cpu_percent(
    previous_snapshot: Optional[CpuSnapshot],
    current_snapshot: Optional[CpuSnapshot],
) -> Optional[float]:
    if previous_snapshot is None or current_snapshot is None:
        return None

    total_delta = current_snapshot.total - previous_snapshot.total
    idle_delta = current_snapshot.idle - previous_snapshot.idle
    if total_delta <= 0:
        return None

    busy_delta = max(total_delta - idle_delta, 0)
    return (busy_delta / total_delta) * 100
