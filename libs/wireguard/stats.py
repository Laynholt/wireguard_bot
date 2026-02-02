import os
import subprocess

import json
import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Union, Tuple

from enum import Enum
from pydantic import BaseModel, Field

from . import user_control

class TrafficStat(BaseModel):
    """Суммарный трафик (в байтах) за период."""
    received_bytes: int = 0
    sent_bytes: int = 0


class PeriodizedTraffic(BaseModel):
    """Трафик, разбитый по периодам."""
    daily: Dict[str, TrafficStat] = Field(default_factory=dict)
    weekly: Dict[str, TrafficStat] = Field(default_factory=dict)
    monthly: Dict[str, TrafficStat] = Field(default_factory=dict)


class WgPeerData(BaseModel):
    """
    Модель для хранения дополнительной информации о Peer (WireGuard).
    """
    allowed_ips: Optional[str] = None
    endpoint: Optional[str] = None
    latest_handshake: Optional[str] = None
    latest_handshake_at: Optional[str] = None  # ISO 8601 UTC время последнего рукопожатия
    transfer_received: Optional[str] = None
    transfer_sent: Optional[str] = None
    raw_received_bytes: int = 0
    raw_sent_bytes: int = 0
    periods: PeriodizedTraffic = Field(default_factory=PeriodizedTraffic)

class WgPeer(BaseModel):
    """
    Модель для хранения основных данных о Peer (WireGuard).
    """
    public_key: str
    username: str
    available: bool
    data: Optional[WgPeerData] = None

class SortBy(str, Enum):
    """
    Перечисление вариантов сортировки списка WgPeer.
    """
    ALLOWED_IPS = "allowed_ips"
    TRANSFER_SENT = "transfer_sent"


class Period(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

class WgPeerList(BaseModel):
    """
    Модель для хранения списка Peer`ов (WireGuard).
    """
    peers: List[WgPeer] = []
    
    def __contains__(self, username: str) -> bool:
        """
        Позволяет писать: if username in wg_peer_list:
          - True, если в self.peers есть WgPeer с таким username.
        """
        return any(peer.username == username for peer in self.peers)
    

def parse_wg_conf(file_path: str) -> Dict[str, Any]:
    """
    Парсит файл конфигурации WireGuard для извлечения списка пиров и их публичных ключей.

    Args:
        file_path (str): Путь к файлу wg0.conf.

    Returns:
        Dict[str, Any]: Словарь, где ключи - публичные ключи пиров, значения - имена пользователей и статус конфига.
    """
    peers = {}
    with open(file_path, 'r', encoding="utf-8") as f:
        lines = [line.strip() for line in f]

    username = None
    public_key = None
    available = True
    
    for i, line in enumerate(lines):
        # Проверяем, является ли строка "[Peer]" (или "#[Peer]")
        if line.endswith("[Peer]"):
            # Определяем, закомментирована ли
            is_commented = line.startswith("#")
            available = not is_commented

            # Безопасно получаем следующую строку, если существует
            next_line = lines[i+1] if i+1 < len(lines) else ""

            # Если следующая строка начинается с '#',
            # то имя пользователя "прячется" после '#' (или '##')
            if next_line.startswith("#"):
                # Срезаем один или два символа '#', если нужно
                username = next_line.lstrip("#").strip()
            else:
                username = "Unknown"

        elif line.startswith("PublicKey"):
            public_key = line.split('=')[1].strip() + '='
            if username and public_key:
                peers[public_key] = {
                    "username": username,
                    "available": available
                }
            # Сбрасываем для следующего пира
            username = None
            public_key = None

    return peers


def __get_wg_status_from_docker() -> str:
    """
    Выполняет команду wg show в Docker-контейнере WireGuard и возвращает вывод.

    Returns:
        str: Вывод команды wg show.
    """
    result = subprocess.run(['docker', 'exec', 'wireguard', 'wg', 'show', 'wg0'],
                            stdout=subprocess.PIPE)
    return result.stdout.decode('utf-8')


def __process_peer_block(block: List[str], peers: Dict[str, Any]) -> Union[WgPeer,  None]:
    """
    ООбрабатывает блок строк (peer: ..., endpoint: ..., etc.), 
    возвращает объект WgPeer с заполненными полями.

    Args:
        block (List[str]): Список строк (peer: ..., endpoint: ..., etc.)
        peers (Dict[str, Any]): Словарь {public_key: {username: username, available: available}, ...}

    Returns:
        dict: Объект WgPeer с заполненными полями или None, если пользователь не найден в конфиге.
    """
    public_key = block[0].split("peer:")[1].strip()

    endpoint = None
    allowed_ips = None
    latest_handshake = None
    transfer_received = None
    transfer_sent = None

    for line in block[1:]:
        if "endpoint:" in line:
            endpoint = line.split("endpoint:")[1].strip()
        elif "allowed ips:" in line:
            allowed_ips = line.split("allowed ips:")[1].strip()
        elif "latest handshake:" in line:
            latest_handshake = line.split("latest handshake:")[1].strip()
        elif "transfer:" in line:
            transfer_info = line.split("transfer:")[1].strip()
            transfer_received, transfer_sent = transfer_info.split("received,")
            transfer_received = transfer_received.strip()
            transfer_sent = transfer_sent.strip().replace("sent", "").strip()

    user_info = peers.get(public_key)
    if user_info is None:
        return None

    return WgPeer(
        public_key=public_key,
        username=user_info['username'],
        available=user_info['available'],
        data=WgPeerData(
            allowed_ips=allowed_ips,
            endpoint=endpoint,
            latest_handshake=latest_handshake,
            transfer_received=transfer_received,
            transfer_sent=transfer_sent   
        )
    ) 


def __convert_transfer_to_bytes(transfer: Optional[str]) -> int:
    """
    Преобразует строку (например, "6.23 GiB") в байты.

    Args:
        transfer (Optional[str]): Строка вида "6.23 GiB".

    Returns:
        int: Числовое значение в байтах.
    """
    if not transfer:
        return 0
    units = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
    size_str, unit = transfer.split()
    return int(float(size_str) * units[unit])


def __convert_bytes_to_human_readable(num_bytes: int) -> str:
    """
    Преобразует байты в формат GiB (например, "123.45 GiB").
    """
    gib_value = num_bytes / (1024**3)
    return f"{gib_value:.2f} GiB"


def bytes_to_human(num_bytes: int) -> str:
    """
    Публичная обёртка для __convert_bytes_to_human_readable.
    """
    return __convert_bytes_to_human_readable(num_bytes)


def __parse_handshake_to_datetime(handshake_str: Optional[str]) -> Optional[datetime]:
    """
    Конвертирует строку вида '1 minute, 9 seconds ago' в UTC datetime.
    Возвращает None, если строка пустая или не распознана.
    """
    if not handshake_str:
        return None

    s = handshake_str.strip().lower()
    if s in {"n/a", "never"}:
        return None

    # Иногда wg выводит "now"
    if s == "now" or s.startswith("0 "):
        return datetime.now(timezone.utc)

    total_seconds = 0
    units = {
        "second": 1,
        "seconds": 1,
        "minute": 60,
        "minutes": 60,
        "hour": 3600,
        "hours": 3600,
        "day": 86400,
        "days": 86400,
        "week": 604800,
        "weeks": 604800,
    }

    parts = s.replace(" ago", "").replace("и ", "").split(",")
    for part in parts:
        chunk = part.strip()
        if not chunk:
            continue
        tokens = chunk.split()
        if len(tokens) < 2:
            continue
        try:
            value = int(tokens[0])
        except ValueError:
            continue
        unit = tokens[1]
        total_seconds += value * units.get(unit, 0)

    if total_seconds == 0:
        return datetime.now(timezone.utc)

    return datetime.now(timezone.utc) - timedelta(seconds=total_seconds)


def __plural_ru(value: int, forms: tuple[str, str, str]) -> str:
    """
    Возвращает слово во множественном/единственном числе для русского языка.
    forms: (1, 2-4, 5-0)
    """
    value_abs = abs(value)
    mod10 = value_abs % 10
    mod100 = value_abs % 100
    if mod10 == 1 and mod100 != 11:
        return forms[0]
    if 2 <= mod10 <= 4 and not (12 <= mod100 <= 14):
        return forms[1]
    return forms[2]


def __format_timedelta_ru(delta: timedelta) -> str:
    """
    Формирует строку вида '1 минута, 9 секунд назад' максимум с двумя компонентами.
    """
    seconds = int(delta.total_seconds())
    if seconds < 0:
        seconds = 0

    units = [
        (86400, ("день", "дня", "дней")),
        (3600, ("час", "часа", "часов")),
        (60, ("минута", "минуты", "минут")),
        (1, ("секунда", "секунды", "секунд")),
    ]

    parts = []
    for unit_seconds, titles in units:
        if seconds >= unit_seconds:
            value = seconds // unit_seconds
            seconds -= value * unit_seconds
            parts.append(f"{value} {__plural_ru(value, titles)}")
        if len(parts) == 2:
            break

    if not parts:
        parts.append("0 секунд")

    return ", ".join(parts) + " назад"


def __format_handshake_age(handshake_iso: Optional[str], now: Optional[datetime] = None) -> Optional[str]:
    """
    Возвращает строку с прошедшим временем от moment до now.
    """
    if not handshake_iso:
        return None
    try:
        dt = datetime.fromisoformat(handshake_iso)
    except ValueError:
        return None

    now = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return __format_timedelta_ru(now - dt)


def __period_keys(now: datetime) -> Tuple[str, str, str]:
    """
    Возвращает ключи для daily/weekly/monthly.
    daily: YYYY-MM-DD
    weekly: YYYY-Www (ISO week)
    monthly: YYYY-MM
    """
    date_key = now.strftime("%Y-%m-%d")
    iso_year, iso_week, _ = now.isocalendar()
    week_key = f"{iso_year}-W{iso_week:02d}"
    month_key = now.strftime("%Y-%m")
    return date_key, week_key, month_key


def __update_period_stats(periods: PeriodizedTraffic, delta_received: int, delta_sent: int, now: datetime) -> None:
    """
    Добавляет приращение трафика в текущие сутки/неделю/месяц.
    """
    date_key, week_key, month_key = __period_keys(now)
    for bucket, key in (
        (periods.daily, date_key),
        (periods.weekly, week_key),
        (periods.monthly, month_key),
    ):
        stat = bucket.get(key)
        if stat is None:
            stat = TrafficStat()
            bucket[key] = stat
        stat.received_bytes += delta_received
        stat.sent_bytes += delta_sent


def get_period_usage(data: WgPeerData, period: Period, now: Optional[datetime] = None) -> TrafficStat:
    """
    Возвращает статистику за текущий день/неделю/месяц.
    """
    now = now or datetime.now(timezone.utc)
    date_key, week_key, month_key = __period_keys(now)

    if period == Period.DAILY:
        return data.periods.daily.get(date_key, TrafficStat())
    if period == Period.WEEKLY:
        return data.periods.weekly.get(week_key, TrafficStat())
    if period == Period.MONTHLY:
        return data.periods.monthly.get(month_key, TrafficStat())

    return TrafficStat()


def format_handshake_age(data: WgPeerData, now: Optional[datetime] = None) -> str:
    """
    Публичный помощник для получения строки вида '1 минута, 9 секунд назад'.
    """
    age = __format_handshake_age(data.latest_handshake_at, now)
    return age if age else (data.latest_handshake or "N/A")


def collect_peer_data(peers: Dict[str, Any]) -> WgPeerList:
    """
    1. Получает «сырой» вывод wg show из Docker (wg0).
    2. Разбивает на блоки (peer: ...), вызывает process_peer_block(...) для каждого.
    3. Возвращает список WgPeer (по каждому пир-юзеру).

    Args:
        peers (Dict[str, Any]): Словарь {public_key: {username: username, available: available}, ...} из parse_wg_conf.

    Returns:
        Объект типа WgPeerList.
    """
    wg_status = __get_wg_status_from_docker()
    lines = wg_status.splitlines()
    
    peer_blocks: WgPeerList = WgPeerList()
    current_peer_block: list[str] = []

    for line in lines:
        if line.startswith("peer:"):
            if current_peer_block:
                processed_peer_block = __process_peer_block(current_peer_block, peers)
                if processed_peer_block:
                    peer_blocks.peers.append(processed_peer_block)
                current_peer_block = []
            current_peer_block.append(line.strip())
        elif current_peer_block:
            current_peer_block.append(line.strip())

    # Обработать последний блок
    if current_peer_block:
        processed_peer_block = __process_peer_block(current_peer_block, peers)
        if processed_peer_block:
            peer_blocks.peers.append(processed_peer_block)

    return peer_blocks

    
def write_data_to_json(file_path: str, data: Dict[str, WgPeerData]) -> None:
    """
    Сохраняет Dict[str, WgPeerData] в файл JSON.
    В процессе сериализации каждый объект WgPeerData превращается в словарь.
    """
    # Превращаем каждое значение (WgPeerData) в dict через .dict()
    raw_data = {key: val.model_dump() for key, val in data.items()}

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(raw_data, f, indent=2, ensure_ascii=False)


def read_data_from_json(file_path: str) -> Dict[str, WgPeerData]:
    """
    Загружает Dict[str, WgPeerData] из JSON-файла.
    Если файл не существует, возвращает пустой словарь.
    """
    if not os.path.exists(file_path):
        return {}

    with open(file_path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)  # это Dict[str, dict]

    # Превращаем каждую вложенную dict обратно в объект WgPeerData
    result = {}
    for key, val in raw_data.items():
        # val: dict => WgPeerData(**val)
        data_obj = WgPeerData(**val)

        # Заполняем raw_* из существующих строк, если они не были сохранены ранее (обратная совместимость).
        if data_obj.raw_received_bytes == 0 and data_obj.transfer_received:
            data_obj.raw_received_bytes = __convert_transfer_to_bytes(data_obj.transfer_received)
        if data_obj.raw_sent_bytes == 0 and data_obj.transfer_sent:
            data_obj.raw_sent_bytes = __convert_transfer_to_bytes(data_obj.transfer_sent)

        result[key] = data_obj

    return result


def remove_user_from_log(file_path: str, username: str):
    """
    Удаляет информацию о переданном пользователе в файле логов.
    """
    current_log_data = read_data_from_json(file_path)
    
    if username in current_log_data:
        del current_log_data[username]
        write_data_to_json(file_path, current_log_data)
    

def __merge_results(
    old_data: Dict[str, WgPeerData],
    new_data: Dict[str, WgPeerData],
    now: datetime
) -> Dict[str, WgPeerData]:
    """
    Объединяет старые и новые данные:
    - latest_handshake_at и endpoint перезаписываем при наличии новых
    - transfer_received/transfer_sent — накапливаем через приращения
    - allowed_ips — обновляем при изменении
    - periods — накапливаем приращения в daily/weekly/monthly
    """
    merged = dict(old_data)  # копия

    for user, new_info in new_data.items():
        if user not in merged:
            # Пользователь встречается впервые
            merged[user] = new_info
            __update_period_stats(
                merged[user].periods,
                new_info.raw_received_bytes,
                new_info.raw_sent_bytes,
                now
            )
            merged[user].transfer_received = __convert_bytes_to_human_readable(new_info.raw_received_bytes)
            merged[user].transfer_sent = __convert_bytes_to_human_readable(new_info.raw_sent_bytes)
            merged[user].latest_handshake = __format_handshake_age(new_info.latest_handshake_at, now) or new_info.latest_handshake
            continue

        current = merged[user]

        old_received_raw = current.raw_received_bytes
        old_sent_raw = current.raw_sent_bytes

        new_received_raw = new_info.raw_received_bytes
        new_sent_raw = new_info.raw_sent_bytes

        # Поддержка перезапуска wg0: если счётчики обнулились, считаем дельтой новое значение
        delta_received = new_received_raw - old_received_raw
        delta_sent = new_sent_raw - old_sent_raw
        if delta_received < 0:
            delta_received = new_received_raw
        if delta_sent < 0:
            delta_sent = new_sent_raw

        __update_period_stats(current.periods, delta_received, delta_sent, now)

        # Обновляем накопительные totals
        total_received_bytes = __convert_transfer_to_bytes(current.transfer_received or "0 B") + delta_received
        total_sent_bytes = __convert_transfer_to_bytes(current.transfer_sent or "0 B") + delta_sent
        current.transfer_received = __convert_bytes_to_human_readable(total_received_bytes)
        current.transfer_sent = __convert_bytes_to_human_readable(total_sent_bytes)

        # Сохраняем raw для последующего вычисления дельт
        current.raw_received_bytes = new_received_raw
        current.raw_sent_bytes = new_sent_raw

        # Обновляем latest_handshake
        if new_info.latest_handshake_at:
            current.latest_handshake_at = new_info.latest_handshake_at
        current.latest_handshake = __format_handshake_age(current.latest_handshake_at, now) or new_info.latest_handshake or current.latest_handshake

        # Обновляем прочие поля при наличии
        if new_info.allowed_ips:
            current.allowed_ips = new_info.allowed_ips
        if new_info.endpoint:
            current.endpoint = new_info.endpoint

    return merged


def accumulate_wireguard_stats(
    conf_file_path: str,
    json_file_path: str,
    sort_by: SortBy = SortBy.TRANSFER_SENT,
    reverse_sort: bool = True
) -> Dict[str, WgPeerData]:
    """
    1. Считывает старые результаты из json_file_path (если есть).
    2. Вызывает parse_wg_conf(conf_file_path) -> peers.
    3. collect_peer_data(peers) -> список словарей.
    4. Преобразует список словарей -> dict по username.
    5. merge_results(...) со старыми данными.
    6. Сортирует данные по переданному типу.

    Args:
        conf_file_path (str): Путь к файлу wg0.conf.
        json_file_path (str): Путь к JSON-файлу, куда сохраняем накопленные результаты.
        sort_by (Optional[str]): "allowed_ips" или "transfer_sent".
        reverse_sort (Optional[bool]): Сортировка по возрастанию (False) или убыванию (True).
    
    Returns:
        Возвращает объединенный словарь данных.
    """
    now = datetime.now(timezone.utc)

    # 1. Старые результаты
    old_data = read_data_from_json(json_file_path)

    # 2. Парсим файл конфигурации (получаем {public_key: username})
    peers = parse_wg_conf(conf_file_path)

    # 3. Собираем новые данные (список словарей)
    peer_list = collect_peer_data(peers)

    # 4. Превращаем список словарей в словарь вида {username: {...}}
    #    (ключ — peer['username'])
    new_data: Dict[str, WgPeerData] = {}
    for peer in peer_list.peers:
        if peer.data is None:
            continue
        username = peer.username

        raw_received_bytes = __convert_transfer_to_bytes(peer.data.transfer_received)
        raw_sent_bytes = __convert_transfer_to_bytes(peer.data.transfer_sent)
        handshake_dt = __parse_handshake_to_datetime(peer.data.latest_handshake)

        new_data[username] = WgPeerData(
            allowed_ips=peer.data.allowed_ips,
            endpoint=peer.data.endpoint,
            latest_handshake=peer.data.latest_handshake,
            latest_handshake_at=handshake_dt.isoformat() if handshake_dt else None,
            transfer_received=peer.data.transfer_received,
            transfer_sent=peer.data.transfer_sent,
            raw_received_bytes=raw_received_bytes,
            raw_sent_bytes=raw_sent_bytes
        )

    # 5. Суммируем и сортируем
    merged = __sort_merged_data(
        __merge_results(old_data, new_data, now),
        sort_by=sort_by,
        reverse_sort=reverse_sort
    )

    # Обновляем человекочитаемую строку рукопожатия для всех записей
    for info in merged.values():
        info.latest_handshake = format_handshake_age(info, now)
    
    return merged


def __sort_merged_data(merged_data: Dict[str, WgPeerData], sort_by: SortBy, reverse_sort: bool) -> Dict[str, WgPeerData]:
    """
    Сортирует словарь {username: WgPeerData} по одному из критериев:
      - "allowed_ips" (в порядке возрастания IP)
      - "transfer_sent" (по убыванию объёма трафика)
    
    Возвращает НОВЫЙ словарь в отсортированном порядке ключей.
    """
    if sort_by == SortBy.ALLOWED_IPS:
        # Сортируем по IP, если есть, иначе 0.0.0.0/32
        sorted_keys = sorted(
            merged_data.keys(),
            key=lambda k: ipaddress.ip_network(
                merged_data[k].allowed_ips.split("/")[0]
            ) if merged_data[k].allowed_ips else ipaddress.ip_network("0.0.0.0/32"),
            reverse=reverse_sort
        )
    elif sort_by == SortBy.TRANSFER_SENT:
        # Сортируем по объёму переданных данных (по убыванию)
        sorted_keys = sorted(
            merged_data.keys(),
            key=lambda k: __convert_transfer_to_bytes(merged_data[k].transfer_sent or "0 B"),
            reverse=reverse_sort
        )
    else:
        # Если критерий не распознан, не сортируем
        sorted_keys = list(merged_data.keys())

    # Создаём новый словарь в требуемом порядке
    return {key: merged_data[key] for key in sorted_keys}


def display_merged_data(merged_data: Dict[str, WgPeerData]) -> None:
    """
    Выводит (print) информацию о каждом пире из переданного словаря.

    Args:
        merged_data (Dict[str, WgPeerData]): Объединенные данные после функции accumulate_wireguard_stats().
    """
    if not merged_data:
        print("Нет данных по ни одному конфигу.")
        return
    
    ORANGE = '\033[33m'
    RED = '\033[31m'
    RESET = '\033[0m'

    commented_users = user_control.get_inactive_usernames()

    for i, (user_name, user_data) in enumerate(merged_data.items(), start=1):
        username_colored = f"{ORANGE}{user_name}{RESET}"
        not_available = f'{RED}[Временно недоступен]{RESET}'
        print(f"{i:2}] User: {username_colored} {not_available if user_name in commented_users else ''}")

        day_stat = get_period_usage(user_data, Period.DAILY)
        week_stat = get_period_usage(user_data, Period.WEEKLY)
        month_stat = get_period_usage(user_data, Period.MONTHLY)
        handshake_str = format_handshake_age(user_data)

        if user_data.allowed_ips:
            print(f"  allowed ips: {user_data.allowed_ips}")
        if user_data.endpoint:
            print(f"  endpoint: {user_data.endpoint}")
        if user_data.latest_handshake:
            print(f"  latest handshake: {handshake_str}")
        if user_data.transfer_received and user_data.transfer_sent:
            print(f"  transfer: {user_data.transfer_received} received, {user_data.transfer_sent} sent")
        print(f"  daily:   {bytes_to_human(day_stat.sent_bytes)} sent, {bytes_to_human(day_stat.received_bytes)} received")
        print(f"  weekly:  {bytes_to_human(week_stat.sent_bytes)} sent, {bytes_to_human(week_stat.received_bytes)} received")
        print(f"  monthly: {bytes_to_human(month_stat.sent_bytes)} sent, {bytes_to_human(month_stat.received_bytes)} received")
        print(f"  total:   {user_data.transfer_sent or '0 B'} sent, {user_data.transfer_received or '0 B'} received")

        print()
