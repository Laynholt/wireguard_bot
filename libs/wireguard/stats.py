import os
import subprocess

import json
import ipaddress
from typing import Optional, List, Dict, Any


def parse_wg_conf(file_path: str) -> dict:
    """
    Парсит файл конфигурации WireGuard для извлечения списка пиров и их публичных ключей.

    Args:
        file_path (str): Путь к файлу wg0.conf.

    Returns:
        dict: Словарь, где ключи - публичные ключи пиров, значения - имена пользователей.
    """
    peers = {}
    with open(file_path, 'r') as file:
        lines = file.readlines()

    username = None
    public_key = None
    for i, line in enumerate(lines):
        line = line.strip()
        if line == "[Peer]":
            # Следующая строка, предположительно, это комментарий с именем пользователя
            username_line = lines[i + 1].strip()
            if username_line.startswith("#"):
                username = username_line[1:].strip()  # Извлекаем имя пользователя
            else:
                username = "Unknown"  # Если комментарий отсутствует
        elif line.startswith("PublicKey"):
            public_key = line.split('=')[1].strip() + '='  # Обрабатываем публичный ключ
            if username and public_key:
                peers[public_key] = username

            # Сбрасываем значения для следующего пира
            username = None
            public_key = None
    return peers


def get_wg_status_from_docker() -> str:
    """
    Выполняет команду wg show в Docker-контейнере WireGuard и возвращает вывод.

    Returns:
        str: Вывод команды wg show.
    """
    result = subprocess.run(['docker', 'exec', 'wireguard', 'wg', 'show', 'wg0'],
                            stdout=subprocess.PIPE)
    return result.stdout.decode('utf-8')


def process_peer_block(block: List[str], peers: dict) -> dict:
    """
    Обрабатывает блок (строки) о пире для извлечения необходимых данных.

    Args:
        block (List[str]): Список строк (peer: ..., endpoint: ..., etc.)
        peers (dict): Словарь {public_key: username, ...}

    Returns:
        dict: Словарь с полями ('username', 'latest_handshake', 'transfer_received', 'transfer_sent', и др.)
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

    user_info = peers.get(public_key, "Unknown")

    return {
        'public_key': public_key,
        'username': user_info,
        'allowed_ips': allowed_ips,
        'endpoint': endpoint,
        'latest_handshake': latest_handshake,
        'transfer_received': transfer_received,
        'transfer_sent': transfer_sent
    }


def convert_transfer_to_bytes(transfer: Optional[str]) -> int:
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


def collect_peer_data(peers: dict, sort_by: Optional[str] = None) -> List[dict]:
    """
    1. Получает «сырой» вывод wg show из Docker (wg0).
    2. Разбивает на блоки (peer: ...), вызывает process_peer_block(...) для каждого.
    3. Сортирует список, если задан sort_by (allowed_ips или transfer_sent).
    4. Возвращает список словарей (по каждому пир-юзеру).

    Args:
        peers (dict): Словарь {public_key: username, ...} из parse_wg_conf.
        sort_by (Optional[str]): Поле, по которому сортировать ("allowed_ips" или "transfer_sent").

    Returns:
        List[dict]: Список словарей вида:
            [
              {
                "username": str,
                "public_key": str,
                "latest_handshake": str | None,
                "transfer_received": str | None,
                "transfer_sent": str | None,
                "endpoint": str | None,
                "allowed_ips": str | None
              },
              ...
            ]
    """
    wg_status = get_wg_status_from_docker()
    lines = wg_status.splitlines()
    peer_blocks = []
    current_peer_block = []

    for line in lines:
        if line.startswith("peer:"):
            if current_peer_block:
                peer_blocks.append(process_peer_block(current_peer_block, peers))
                current_peer_block = []
            current_peer_block.append(line.strip())
        elif current_peer_block:
            current_peer_block.append(line.strip())

    # Обработать последний блок
    if current_peer_block:
        peer_blocks.append(process_peer_block(current_peer_block, peers))

    # Сортировка
    if sort_by == "allowed_ips":
        def sort_key_ips(peer_data: dict) -> ipaddress.IPv4Network:
            if peer_data["allowed_ips"]:
                return ipaddress.ip_network(peer_data["allowed_ips"].split("/")[0])
            return ipaddress.ip_network("0.0.0.0/32")
        peer_blocks.sort(key=sort_key_ips)

    elif sort_by == "transfer_sent":
        peer_blocks.sort(
            key=lambda x: convert_transfer_to_bytes(x["transfer_sent"]),
            reverse=True
        )

    return peer_blocks


def display_peer_list(peer_list: List[dict]) -> None:
    """
    Выводит (print) информацию о каждом пире из списка словарей.

    Args:
        peer_list (List[dict]): Список словарей, возвращаемый collect_peer_data().
    """
    ORANGE = '\033[33m'
    RESET = '\033[0m'

    for peer in peer_list:
        username_colored = f"{ORANGE}{peer['username']}{RESET}"
        print(f"User: {username_colored} ({peer['public_key']})")

        if peer['allowed_ips']:
            print(f"  allowed ips: {peer['allowed_ips']}")
        if peer['endpoint']:
            print(f"  endpoint: {peer['endpoint']}")
        if peer['latest_handshake']:
            print(f"  latest handshake: {peer['latest_handshake']}")
        if peer['transfer_received'] and peer['transfer_sent']:
            print(f"  transfer: {peer['transfer_received']} received, {peer['transfer_sent']} sent")

        print()


def display_wg_status_with_names(peers: dict, sort_by: Optional[str] = None) -> None:
    """
    Функция, оставленная для совместимости,
    которая теперь просто вызывает collect_peer_data(...) + display_peer_list(...).

    Args:
        peers (dict): Словарь {public_key: username, ...}.
        sort_by (Optional[str]): "allowed_ips" или "transfer_sent".
    """
    peer_list = collect_peer_data(peers, sort_by=sort_by)
    display_peer_list(peer_list)


def read_previous_results_json(file_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Считывает предыдущие результаты из JSON-файла. Если файла нет, возвращает пустой словарь.
    Формат:
    {
      "username": {
        "latest_handshake": "...",
        "transfer_received": "... GiB",
        "transfer_sent": "... GiB",
        "allowed_ips": "...",
        "endpoint": "..."
      },
      ...
    }
    """
    if not os.path.exists(file_path):
        return {}
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_results_json(file_path: str, data: Dict[str, Dict[str, Any]]) -> None:
    """
    Перезаписывает JSON-файл новыми данными (data).
    """
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def convert_bytes_to_human_readable(num_bytes: int) -> str:
    """
    Преобразует байты в формат GiB (например, "123.45 GiB").
    """
    gib_value = num_bytes / (1024**3)
    return f"{gib_value:.2f} GiB"


def merge_results(
    old_data: Dict[str, Dict[str, Any]],
    new_data: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Объединяет старые и новые данные:
    - latest_handshake перезаписываем
    - transfer_received/transfer_sent — суммируем
    - allowed_ips/endpoint — тоже обновляем (по желанию)
    """
    merged = dict(old_data)  # копия

    for user, new_info in new_data.items():
        if user not in merged:
            # Пользователь встречается впервые
            merged[user] = new_info
            continue

        old_received = merged[user].get("transfer_received", "0 B")
        old_sent = merged[user].get("transfer_sent", "0 B")
        new_received = new_info.get("transfer_received", "0 B")
        new_sent = new_info.get("transfer_sent", "0 B")

        sum_received = convert_transfer_to_bytes(old_received) + convert_transfer_to_bytes(new_received)
        sum_sent = convert_transfer_to_bytes(old_sent) + convert_transfer_to_bytes(new_sent)

        # Обновляем latest_handshake
        merged[user]["latest_handshake"] = new_info.get("latest_handshake", "N/A")

        # Сохраняем суммированный трафик
        merged[user]["transfer_received"] = convert_bytes_to_human_readable(sum_received)
        merged[user]["transfer_sent"] = convert_bytes_to_human_readable(sum_sent)

        # При желании обновляем и другие поля
        if "allowed_ips" in new_info:
            merged[user]["allowed_ips"] = new_info["allowed_ips"]
        if "endpoint" in new_info:
            merged[user]["endpoint"] = new_info["endpoint"]

    return merged


def accumulate_wireguard_stats(
    conf_file_path: str,
    json_file_path: str,
    sort_by: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
    """
    1. Считывает старые результаты из json_file_path (если есть).
    2. Вызывает parse_wg_conf(conf_file_path) -> peers.
    3. collect_peer_data(peers, sort_by) -> список словарей.
    4. Преобразует список словарей -> dict по username.
    5. merge_results(...) со старыми данными.
    6. write_results_json(...).

    Args:
        conf_file_path (str): Путь к файлу wg0.conf.
        json_file_path (str): Путь к JSON-файлу, куда сохраняем накопленные результаты.
        sort_by (Optional[str]): "allowed_ips" или "transfer_sent".
    
    Returns:
        Возвращает объединенный словарь данных.
    """
    # 1. Старые результаты
    old_data = read_previous_results_json(json_file_path)

    # 2. Парсим файл конфигурации (получаем {public_key: username})
    peers = parse_wg_conf(conf_file_path)

    # 3. Собираем новые данные (список словарей)
    peer_list = collect_peer_data(peers, sort_by=sort_by)

    # 4. Превращаем список словарей в словарь вида {username: {...}}
    #    (ключ — peer['username'])
    new_data: Dict[str, Dict[str, Any]] = {}
    for peer in peer_list:
        username = peer["username"]
        new_data[username] = {
            "latest_handshake": peer["latest_handshake"],
            "transfer_received": peer["transfer_received"],
            "transfer_sent": peer["transfer_sent"],
            "allowed_ips": peer["allowed_ips"],
            "endpoint": peer["endpoint"]
        }

    # 5. Суммируем
    merged = merge_results(old_data, new_data)

    # 6. Сохраняем
    write_results_json(json_file_path, merged)
    print(f"[+] Логи Wireguard успешно обновлены и сохранены в [{json_file_path}]")

    return merged