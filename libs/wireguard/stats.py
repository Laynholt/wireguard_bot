import os
import subprocess

import json
import ipaddress
from typing import Optional, List, Dict, Any, Union

from enum import Enum
from pydantic import BaseModel

from . import user_control

class WgPeerData(BaseModel):
    """
    Модель для хранения дополнительной информации о Peer (WireGuard).
    """
    allowed_ips: Optional[str] = None
    endpoint: Optional[str] = None
    latest_handshake: Optional[str] = None
    transfer_received: Optional[str] = None
    transfer_sent: Optional[str] = None

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
    
    def sort_peers(self, sort_by: SortBy) -> None:
        """
        Inline-сортировка по одному из двух критериев: 
        1) ALLOWED_IPS
        2) TRANSFER_SENT
        """
        if sort_by == SortBy.ALLOWED_IPS:
            def sort_key_ips(peer: WgPeer):
                if peer.data.allowed_ips:
                    return ipaddress.ip_network(peer.data.allowed_ips.split("/")[0])
                return ipaddress.ip_network("0.0.0.0/32")

            self.peers.sort(key=sort_key_ips)

        elif sort_by == SortBy.TRANSFER_SENT:
            self.peers.sort(
                key=lambda p: __convert_transfer_to_bytes(p.data.transfer_sent or "0 B"),
                reverse=True
            )
    

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


def collect_peer_data(peers: Dict[str, Any], sort_by: Optional[SortBy] = None) -> WgPeerList:
    """
    1. Получает «сырой» вывод wg show из Docker (wg0).
    2. Разбивает на блоки (peer: ...), вызывает process_peer_block(...) для каждого.
    3. Сортирует список, если задан sort_by.
    4. Возвращает список WgPeer (по каждому пир-юзеру).

    Args:
        peers (Dict[str, Any]): Словарь {public_key: {username: username, available: available}, ...} из parse_wg_conf.
        sort_by (Optional[str]): Поле, по которому сортировать ("allowed_ips" или "transfer_sent").

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

    if sort_by:
        peer_blocks.sort_peers(sort_by)

    return peer_blocks


def __display_peer_list(peer_list: WgPeerList) -> None:
    """
    Выводит (print) информацию о каждом пире из списка WgPeer.

    Args:
        peer_list (WgPeerList): Список WgPeer, возвращаемый collect_peer_data().
    """
    if not peer_list:
        print("Нет данных по ни одному конфигу.")
        return
    
    ORANGE = '\033[33m'
    RED = '\033[31m'
    RESET = '\033[0m'

    for i, peer in enumerate(peer_list.peers, start=1):
        username_colored = f"{ORANGE}{peer.username}{RESET}"
        not_available = f'{RED}[Временно недоступен]{RESET}'
        print(f"{i:2}] User: {username_colored} ({peer.public_key}) {not_available if not peer.available else ''}")

        if peer.data.allowed_ips:
            print(f"  allowed ips: {peer.data.allowed_ips}")
        if peer.data.endpoint:
            print(f"  endpoint: {peer.data.endpoint}")
        if peer.data.latest_handshake:
            print(f"  latest handshake: {peer.data.latest_handshake}")
        if peer.data.transfer_received and peer.data.transfer_sent:
            print(f"  transfer: {peer.data.transfer_received} received, {peer.data.transfer_sent} sent")

        print()


def display_wg_status_with_names(peers: Dict[str, Any], sort_by: Optional[str] = None) -> None:
    """
    Функция, оставленная для совместимости,
    которая теперь просто вызывает collect_peer_data(...) + display_peer_list(...).

    Args:
        peers (Dict[str, Any]): Словарь {public_key: {username: username, available: available}, ...}.
        sort_by (Optional[str]): "allowed_ips" или "transfer_sent".
    """
    peer_list = collect_peer_data(peers, sort_by=sort_by)
    __display_peer_list(peer_list)

    
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
        result[key] = WgPeerData(**val)

    return result


def __merge_results(
    old_data: Dict[str, WgPeerData],
    new_data: Dict[str, WgPeerData]
) -> Dict[str, WgPeerData]:
    """
    Объединяет старые и новые данные:
    - latest_handshake и endpoint перезаписываем
    - transfer_received/transfer_sent — суммируем
    - allowed_ips — тоже обновляем
    """
    merged = dict(old_data)  # копия

    for user, new_info in new_data.items():
        if user not in merged:
            # Пользователь встречается впервые
            merged[user] = new_info
            continue

        old_received = merged[user].transfer_received or "0 B"
        old_sent = merged[user].transfer_sent or "0 B"
        new_received = new_info.transfer_received or "0 B"
        new_sent = new_info.transfer_sent or "0 B"

        sum_received = __convert_transfer_to_bytes(old_received) + __convert_transfer_to_bytes(new_received)
        sum_sent = __convert_transfer_to_bytes(old_sent) + __convert_transfer_to_bytes(new_sent)

        # Обновляем latest_handshake
        merged[user].latest_handshake = new_info.latest_handshake or "N/A"

        # Сохраняем суммированный трафик
        merged[user].transfer_received = __convert_bytes_to_human_readable(sum_received)
        merged[user].transfer_sent = __convert_bytes_to_human_readable(sum_sent)

        # При желании обновляем и другие поля
        if new_info.allowed_ips:
            merged[user].allowed_ips = new_info.allowed_ips
        if new_info.endpoint:
            merged[user].endpoint = new_info.endpoint

    return merged


def accumulate_wireguard_stats(
    conf_file_path: str,
    json_file_path: str,
    sort_by: Optional[str] = None
) -> Dict[str, WgPeerData]:
    """
    1. Считывает старые результаты из json_file_path (если есть).
    2. Вызывает parse_wg_conf(conf_file_path) -> peers.
    3. collect_peer_data(peers, sort_by) -> список словарей.
    4. Преобразует список словарей -> dict по username.
    5. merge_results(...) со старыми данными.

    Args:
        conf_file_path (str): Путь к файлу wg0.conf.
        json_file_path (str): Путь к JSON-файлу, куда сохраняем накопленные результаты.
        sort_by (Optional[str]): "allowed_ips" или "transfer_sent".
    
    Returns:
        Возвращает объединенный словарь данных.
    """
    # 1. Старые результаты
    old_data = read_data_from_json(json_file_path)

    # 2. Парсим файл конфигурации (получаем {public_key: username})
    peers = parse_wg_conf(conf_file_path)

    # 3. Собираем новые данные (список словарей)
    peer_list = collect_peer_data(peers, sort_by=sort_by)

    # 4. Превращаем список словарей в словарь вида {username: {...}}
    #    (ключ — peer['username'])
    new_data: Dict[str, WgPeerData] = {}
    for peer in peer_list.peers:
        username = peer.username
        new_data[username] = WgPeerData(
            allowed_ips=peer.data.allowed_ips,
            endpoint=peer.data.endpoint,
            latest_handshake=peer.data.latest_handshake,
            transfer_received=peer.data.transfer_received,
            transfer_sent=peer.data.transfer_sent
        )

    # 5. Суммируем
    merged = __merge_results(old_data, new_data)
    return merged


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

        if user_data.allowed_ips:
            print(f"  allowed ips: {user_data.allowed_ips}")
        if user_data.endpoint:
            print(f"  endpoint: {user_data.endpoint}")
        if user_data.latest_handshake:
            print(f"  latest handshake: {user_data.latest_handshake}")
        if user_data.transfer_received and user_data.transfer_sent:
            print(f"  transfer: {user_data.transfer_received} received, {user_data.transfer_sent} sent")

        print()