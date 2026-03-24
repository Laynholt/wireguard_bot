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


@dataclass
class ProcessCpuSample:
    total_jiffies: int
    name: str


@dataclass
class ProcessUsage:
    pid: int
    name: str
    percent: float
    used_mb: int | None = None


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


def read_process_cpu_samples() -> dict[int, ProcessCpuSample]:
    proc_path = "/proc"
    samples: dict[int, ProcessCpuSample] = {}

    try:
        entries = os.scandir(proc_path)
    except (FileNotFoundError, PermissionError, OSError):
        return samples

    with entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue

            pid = int(entry.name)
            sample = _read_process_cpu_sample(pid)
            if sample is not None:
                samples[pid] = sample

    return samples


def calculate_top_cpu_processes(
    previous_snapshot: Optional[CpuSnapshot],
    current_snapshot: Optional[CpuSnapshot],
    previous_samples: Optional[dict[int, ProcessCpuSample]],
    current_samples: Optional[dict[int, ProcessCpuSample]],
    limit: int = 5,
) -> list[ProcessUsage]:
    if (
        previous_snapshot is None
        or current_snapshot is None
        or previous_samples is None
        or current_samples is None
    ):
        return []

    total_delta = current_snapshot.total - previous_snapshot.total
    if total_delta <= 0:
        return []

    usages: list[ProcessUsage] = []
    for pid, current_sample in current_samples.items():
        previous_sample = previous_samples.get(pid)
        if previous_sample is None:
            continue

        process_delta = current_sample.total_jiffies - previous_sample.total_jiffies
        if process_delta <= 0:
            continue

        usages.append(
            ProcessUsage(
                pid=pid,
                name=current_sample.name,
                percent=(process_delta / total_delta) * 100,
            )
        )

    usages.sort(key=lambda item: item.percent, reverse=True)
    return usages[: max(limit, 1)]


def collect_top_memory_processes(
    total_memory_mb: int,
    limit: int = 5,
) -> list[ProcessUsage]:
    if total_memory_mb <= 0:
        return []

    total_memory_bytes = total_memory_mb * 1024 * 1024
    page_size = _get_page_size()
    usages: list[ProcessUsage] = []

    try:
        entries = os.scandir("/proc")
    except (FileNotFoundError, PermissionError, OSError):
        return []

    with entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue

            usage = _read_process_memory_usage(
                pid=int(entry.name),
                page_size=page_size,
                total_memory_bytes=total_memory_bytes,
            )
            if usage is not None:
                usages.append(usage)

    usages.sort(key=lambda item: item.percent, reverse=True)
    return usages[: max(limit, 1)]


def _read_process_cpu_sample(pid: int) -> Optional[ProcessCpuSample]:
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8", errors="replace") as stat_file:
            stat_line = stat_file.readline().strip()
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return None

    comm_start = stat_line.find("(")
    comm_end = stat_line.rfind(")")
    if comm_start == -1 or comm_end == -1 or comm_end <= comm_start:
        return None

    name = stat_line[comm_start + 1 : comm_end].strip() or str(pid)
    suffix_fields = stat_line[comm_end + 1 :].strip().split()
    if len(suffix_fields) <= 12:
        return None

    try:
        utime = int(suffix_fields[11])
        stime = int(suffix_fields[12])
    except ValueError:
        return None

    return ProcessCpuSample(total_jiffies=utime + stime, name=name)


def _read_process_memory_usage(
    pid: int,
    page_size: int,
    total_memory_bytes: int,
) -> Optional[ProcessUsage]:
    try:
        with open(f"/proc/{pid}/statm", "r", encoding="utf-8", errors="replace") as statm_file:
            fields = statm_file.readline().split()
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return None

    if len(fields) < 2:
        return None

    try:
        rss_pages = int(fields[1])
    except ValueError:
        return None

    if rss_pages <= 0:
        return None

    rss_bytes = rss_pages * page_size
    return ProcessUsage(
        pid=pid,
        name=_read_process_name(pid),
        percent=(rss_bytes / total_memory_bytes) * 100 if total_memory_bytes else 0.0,
        used_mb=int(rss_bytes / (1024 * 1024)),
    )


def _read_process_name(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/comm", "r", encoding="utf-8", errors="replace") as comm_file:
            name = comm_file.readline().strip()
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return str(pid)

    return name or str(pid)


def _get_page_size() -> int:
    try:
        return os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, ValueError, OSError):
        return 4096
