import argparse
import subprocess
import ipaddress
from typing import Optional

from libs.wireguard import config  # Для корректной сортировки IP-адресов

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
    result = subprocess.run(['docker', 'exec', 'wireguard', 'wg', 'show', 'wg0'], stdout=subprocess.PIPE)
    return result.stdout.decode('utf-8')

def display_wg_status_with_names(peers: dict, sort_by: Optional[str] = None):
    """
    Отображает статус пиров с возможностью сортировки по IP или объему переданных данных.

    Args:
        peers (dict): Словарь с публичными ключами и именами пользователей.
        sort_by (str): Поле, по которому будет произведена сортировка (allowed_ips или transfer_sent).
    """
    wg_status = get_wg_status_from_docker()

    # Разделяем вывод построчно
    lines = wg_status.splitlines()
    peer_blocks = []
    current_peer_block = []

    for line in lines:
        # Сначала проверим, начинается ли новая секция peer
        if line.startswith("peer:"):
            # Если в current_peer_block есть данные, значит, мы собрали предыдущий блок и можем его обработать
            if current_peer_block:
                peer_blocks.append(process_peer_block(current_peer_block, peers))
                current_peer_block = []

            # Начинаем новый блок
            current_peer_block.append(line.strip())
        elif current_peer_block:
            # Собираем строки текущего блока, пока не встретится новый peer
            current_peer_block.append(line.strip())

    # Обрабатываем последний блок, если он есть
    if current_peer_block:
        peer_blocks.append(process_peer_block(current_peer_block, peers))

    # Сортировка по выбранному полю
    if sort_by == "allowed_ips":
        peer_blocks.sort(key=lambda x: ipaddress.ip_network(x['allowed_ips'].split("/")[0]))
    elif sort_by == "transfer_sent":
        peer_blocks.sort(key=lambda x: convert_transfer_to_bytes(x['transfer_sent']) if x['transfer_sent'] else 0, reverse=True)

    # Выводим блоки после сортировки
    for peer in peer_blocks:
        display_peer_info(peer)

def process_peer_block(block: list, peers: dict) -> dict:
    """
    Обрабатывает блок пира для извлечения необходимых данных.

    Args:
        block (list): Список строк с информацией о пире.
        peers (dict): Словарь с публичными ключами и именами пользователей.

    Returns:
        dict: Словарь с полями для отображения информации о пире.
    """
    public_key = block[0].split("peer:")[1].strip()

    endpoint = None
    allowed_ips = None
    latest_handshake = None
    transfer_received = None
    transfer_sent = None

    # Проходим по каждой строке блока и ищем нужные поля
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
    username = user_info

    return {
        'public_key': public_key,
        'username': username,
        'allowed_ips': allowed_ips,
        'endpoint': endpoint,
        'latest_handshake': latest_handshake,
        'transfer_received': transfer_received,
        'transfer_sent': transfer_sent
    }

def display_peer_info(peer: dict):
    """
    Отображает информацию о пире, включая имя пользователя и данные соединения.

    Args:
        peer (dict): Словарь с информацией о пире.
    """
    # ANSI код для оранжевого цвета
    ORANGE = '\033[33m'
    RESET = '\033[0m'

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

    print()  # пустая строка для разделения пиров

# Вспомогательная функция для преобразования данных о передаче в байты
def convert_transfer_to_bytes(transfer: str) -> int:
    """
    Преобразует строку с объемом переданных данных в байты.

    Args:
        transfer (str): Строка с объемом данных и единицами измерения.

    Returns:
        int: Объем данных в байтах.
    """
    if transfer is None:
        return 0
    units = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
    size, unit = transfer.split()
    return int(float(size) * units[unit])

if __name__ == "__main__":
    # Путь к файлу wg0.conf
    conf_file_path = f'{config.wireguard_folder}/config/wg_confs/wg0.conf'

    # Парсим аргументы командной строки
    parser = argparse.ArgumentParser(description="WireGuard peer status with sorting options.")
    parser.add_argument('-s', '--sort', choices=['allowed_ips', 'transfer_sent'],
                        help="Specify the sorting option: 'allowed_ips' or 'transfer_sent'.")
    args = parser.parse_args()

    # Парсим файл конфигурации
    peers = parse_wg_conf(conf_file_path)

    # Проверяем, передан ли аргумент сортировки
    if args.sort:
        # Если передан параметр сортировки, используем его
        display_wg_status_with_names(peers, sort_by=args.sort)
    else:
        # Если параметр сортировки не передан, предлагаем выбрать вручную
        print("Choose sorting option:")
        print("1. Sort by allowed_ips")
        print("2. Sort by transfer_sent")

        sort_option = input("Enter choice (1 or 2): ").strip()
        if sort_option == "1":
            display_wg_status_with_names(peers, sort_by="allowed_ips")
        elif sort_option == "2":
            display_wg_status_with_names(peers, sort_by="transfer_sent")
        else:
            print("Invalid choice")