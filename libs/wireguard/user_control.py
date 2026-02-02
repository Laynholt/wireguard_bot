import os
import re
import pwd
from typing import List, Literal, Optional, Dict, Any
import zipfile
import ipaddress
from enum import Enum
import json
import shutil
from datetime import datetime

from . import wg_db

from ..core import config
from . import utils
from . import stats


class UserModifyType(Enum):
    REMOVE = 1
    COMMENT_UNCOMMENT = 2


class UserState(Enum):
    COMMENTED = 1
    UNCOMMENTED = 0


class ActionType(Enum):
    COMMENT = 2
    UNCOMMENT = 3


def __get_key(filename: str) -> str:
    """
    Получает ключ из файла.

    Args:
        filename (str): Путь к файлу.

    Returns:
        str: Ключ из файла.
    """
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            key = file.readline()
            return key.strip()
    except IOError:
        print(f'Не удалось открыть файл [{filename}] для чтения ключа!')
        return ''


def migrate_legacy_users_to_db() -> None:
    """
    Мигрирует пользователей из старой структуры папок в SQLite.
    - Читает legacy stats.json (если есть) для списка имён.
    - Собирает ключи из /config/<user>/public|private|preshared files.
    - created_at берётся из ctime папки.
    - Если миграция успешна, удаляет папку пользователя.
    - Пропускает пользователей, у которых нет ключей или папки.
    """
    wg_db.init_db()

    legacy_stats: Dict[str, Any] = {}
    stats_path = config.wireguard_log_filepath
    if os.path.exists(stats_path):
        try:
            with open(stats_path, "r", encoding="utf-8") as f:
                legacy_stats = json.load(f)
        except Exception:
            legacy_stats = {}

    base_dir = os.path.join(config.wireguard_folder, "config")
    entries = [
        d for d in os.listdir(base_dir)
        if d not in config.system_names and os.path.isdir(os.path.join(base_dir, d))
    ]

    usernames = {name.lstrip("+") for name in entries}.union(set(legacy_stats.keys()))

    for username in usernames:
        folder = os.path.join(base_dir, username)
        commented_folder = os.path.join(base_dir, f"+{username}")
        folder_path = None
        commented_flag = 0
        if os.path.isdir(folder):
            folder_path = folder
        elif os.path.isdir(commented_folder):
            folder_path = commented_folder
            commented_flag = 1
        if folder_path is None:
            continue

        priv_path = os.path.join(folder_path, f"privatekey-{username}")
        pub_path = os.path.join(folder_path, f"publickey-{username}")
        psk_path = os.path.join(folder_path, f"presharedkey-{username}")

        if not (os.path.exists(priv_path) and os.path.exists(pub_path) and os.path.exists(psk_path)):
            continue

        private_key = __get_key(priv_path)
        public_key = __get_key(pub_path)
        preshared_key = __get_key(psk_path)

        created_at = datetime.fromtimestamp(os.path.getctime(folder_path)).isoformat()
        stats_blob = legacy_stats.get(username)
        stats_json = json.dumps(stats_blob, ensure_ascii=False) if isinstance(stats_blob, dict) else None

        wg_db.upsert_user(
            name=username,
            private_key=private_key,
            public_key=public_key,
            preshared_key=preshared_key,
            created_at=created_at,
            commented=commented_flag,
            stats_json=stats_json,
        )

        try:
            shutil.rmtree(folder_path)
        except Exception:
            pass
    

def __error_exit(user_name: str) -> None:
    """
    Обрабатывает ошибочные ситуации и выполняет откат изменений.

    Args:
        user_name (str): Имя пользователя.
    """
    filename = config.wireguard_config_filepath
    command = (
        f'docker exec wireguard bash -c "' 
        f'rm -r /config/{user_name}'
    )
    utils.run_command(command).return_with_print()

    if os.path.exists(f'{filename}.bak'):
        utils.run_command(f'mv {filename}.bak {filename}').return_with_print()

    print(f'[{50*"-"}]\n')


def __get_next_available_ip() -> utils.FunctionResult:
    """
    Ищет следующий доступный IP-адрес для пользователя.

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и доступный IP-адрес или описание ошибки.
    """
    filename = config.wireguard_config_filepath
    busy_ips = []

    try:
        with open(filename, 'r', encoding='utf-8') as file:
            for line in file:
                if 'AllowedIPs' in line:
                    ip = line.split('=')[1].strip().split('/')[0]
                    ip_octet = int(ip.split('.')[3])
                    busy_ips.append(ip_octet)
        
        for i in range(2, 255):
            if i not in busy_ips:
                return utils.FunctionResult(status=True, description=f"{config.local_ip}{i}/32")
        
        return utils.FunctionResult(status=False, description='Все IP-адреса в диапазоне заняты!')
    except IOError:
        return utils.FunctionResult(status=False, description=f'Не удалось открыть файл [{filename}] для анализа IP-адресов!')


def __strip_bad_symbols(username: str) -> str:
    """
    Очищает строку от запрещенных символов, оставляя только латинские символы и цифры.
    
    Args:
        username (str): Имя пользователя.
        
    Returns:
        str: Очищенное имя пользователя.
    """
    return re.sub(f'[^{config.allowed_username_pattern}]', '', username)

def __get_dsn_server_ip() -> str:
    """
    Возвращает строку с IP-адресом(ами) DNS-сервера на основе настроек конфигурации.

    Args:
        Нет аргументов, используется глобальный объект config.

    Returns:
        str: Один IP или список IP-адресов, разделённых запятой.
    """
    dns_raw: str = config.dns_server_name.strip()

    # Поддержка нескольких IP/значений через пробел или запятую:
    # пример: "1.1.1.1, 8.8.8.8" или "1.1.1.1 8.8.8.8"
    dns_tokens: List[str] = [t for t in re.split(r"[,\s]+", dns_raw) if t]

    def _get_valid_ips(tokens: List[str]) -> List[str]:
        """
        Возвращает список всех валидных IP-адресов из списка строк.
        """
        valid_ips: List[str] = []
        for token in tokens:
            try:
                ipaddress.ip_address(token)
            except ValueError:
                continue
            else:
                valid_ips.append(token)
        return valid_ips

    # 1. DNS-сервер НЕ в Docker
    if not config.is_dns_server_in_docker:
        # Пользователь мог указать один или несколько IP
        valid_ips = _get_valid_ips(dns_tokens)
        if valid_ips:
            # Вернём все валидные IP через запятую
            return ", ".join(valid_ips)

        # Не IP и не список IP → используем локальный адрес по умолчанию
        return f"{config.local_ip}1"

    # 2. DNS-сервер в Docker
    # Даже в этом режиме пользователь мог прямо указать один или несколько IP —
    # тогда не дергаем docker inspect.
    valid_ips = _get_valid_ips(dns_tokens)
    if valid_ips:
        return ", ".join(valid_ips)

    # Иначе считаем, что это имя контейнера (берём первый токен как имя)
    dns_container_name: str = dns_tokens[0] if dns_tokens else dns_raw

    ret_val = utils.run_command(
        "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "
        + dns_container_name
    )

    if not ret_val.status:
        ret_val.return_with_print()
        return f"{config.local_ip}1"

    # docker inspect вернёт один IP
    return ret_val.description.strip()


def add_user(user_name: str) -> utils.FunctionResult:
    """
    Основная функция для создания и добавления нового пользователя в конфиг WireGuard.

    Args:
        user_name (str): Имя пользователя, который должен быть добавлен.

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата или ошибки.
    """
    # Добавляем папку logs
    utils.setup_logs_directory()

    names = os.listdir(f'{config.wireguard_folder}/config')
    print(f'\n[{50*"-"}]')

    stripped_user_name = __strip_bad_symbols(user_name)
    if len(user_name) != len(stripped_user_name):
        return utils.FunctionResult(status=False, description=f'Имя пользователя может состоять только из латинских символов и цифр!').return_with_print(
            add_to_print=f'[{50*"-"}]\n')
    
    user_name_commented = f'+{user_name}'

    if user_name in names or user_name_commented in names:
        return utils.FunctionResult(status=False, description=f'Имя [{user_name}] уже существует!').return_with_print(
            add_to_print=f'[{50*"-"}]\n')

    try:
        print(f'Введенное имя успешно обработано и получено: {user_name}.')
        print(f'Создаю ключи для [{user_name}]...')

        command = (
            f'docker exec wireguard bash -c "' 
            f'mkdir -m 777 /config/{user_name} && ' 
            f'wg genkey | tee /config/{user_name}/privatekey-{user_name} | ' 
            f'wg pubkey | tee /config/{user_name}/publickey-{user_name} && ' 
            f'wg genpsk | tee /config/{user_name}/presharedkey-{user_name}"'
        )
        utils.run_command(command).return_with_print()

        print(f'Ключи для [{user_name}] созданы!')

        user_public_key = __get_key(f'{config.wireguard_folder}/config/{user_name}/publickey-{user_name}')
        if not user_public_key:
            return utils.FunctionResult(status=False,
                                  description=f'Публичный ключ пользователя [{user_name}] пуст!').return_with_print(
                                      error_handler=lambda: __error_exit(user_name))

        user_preshared_key = __get_key(f'{config.wireguard_folder}/config/{user_name}/presharedkey-{user_name}')
        if not user_preshared_key:
            return utils.FunctionResult(status=False,
                                  description=f'Предварительный общий ключ пользователя [{user_name}] пуст!').return_with_print(
                                      error_handler=lambda: __error_exit(user_name))
            
        user_private_key = __get_key(f'{config.wireguard_folder}/config/{user_name}/privatekey-{user_name}')
        if not user_private_key:
            return utils.FunctionResult(status=False, description=f'Приватный ключ пользователя [{user_name}] пуст!').return_with_print(
                                      error_handler=lambda: __error_exit(user_name))

        server_public_key = __get_key(f'{config.wireguard_folder}/config/server/publickey-server')
        if not server_public_key:
            return utils.FunctionResult(status=False, description='Публичный ключ сервера пуст!').return_with_print(
                                      error_handler=lambda: __error_exit(user_name))

        print(f'Добавляю [{user_name}] в конфиг...')
        ip_func_result = __get_next_available_ip()
        if ip_func_result.status is False:
            return ip_func_result.return_with_print(error_handler=lambda: __error_exit(user_name))
        allowed_ip = ip_func_result.description

        filename = config.wireguard_config_filepath
        try:
            utils.run_command(f'cp {filename} {filename}.bak').return_with_print()

            with open(filename, 'a', encoding='utf-8') as file:
                file.write(
                    f'[Peer]\n'
                    f'# {user_name}\n'
                    f'PublicKey = {user_public_key}\n'
                    f'PresharedKey = {user_preshared_key}\n'
                    f'AllowedIPs = {allowed_ip}\n\n'
                )
            print(f'Данные для [{user_name}] добавлены в конфиг!')
        except IOError:
            return utils.FunctionResult(status=False,
                                  description=f'Не удалось открыть файл [{filename}] для добавления [{user_name}] в конфиг!').return_with_print(
                                      error_handler=lambda: __error_exit(user_name))

        print(f'Создаю конфиг пользователя {user_name}...\n')
        filename = f'{config.wireguard_folder}/config/{user_name}/{user_name}.conf'
        try:
            with open(filename, 'w', encoding='utf-8') as file:
                file.write(
                    f'[Interface]\n'
                    f'Address = {allowed_ip}\n'
                    f'PrivateKey = {user_private_key}\n'
                    # f'ListenPort = 51820\n'
                    f'DNS = {__get_dsn_server_ip()}\n\n'
                    f'[Peer]\n'
                    f'PublicKey = {server_public_key}\n'
                    f'PresharedKey = {user_preshared_key}\n'
                    f'Endpoint = {config.server_ip}:{config.server_port}\n'
                    f'AllowedIPs = 0.0.0.0/0\n'
                    # f'PersistentKeepalive = 30\n'
                )
        except IOError:
            return utils.FunctionResult(status=False,
                                  description=f'Не удалось открыть файл [{filename}] для записи конфига для [{user_name}]!').return_with_print(
                                      error_handler=lambda: __error_exit(user_name))
        
        command = (
            f'docker exec wireguard bash -c "' 
            f'qrencode -t png -o /config/{user_name}/{user_name}.png -r /config/{user_name}/{user_name}.conf"'
        )
        utils.run_command(command).return_with_print()

        utils.backup_config()

        print(f'Вывожу конфиг пользователя {user_name}:\n')
        command = (
            f'cat {config.wireguard_folder}/config/{user_name}/{user_name}.conf &&' 
            f'docker exec wireguard bash -c "' 
            f'qrencode -t ansiutf8 < /config/{user_name}/{user_name}.conf ;' 
            f'rm /config/wg_confs/wg0.conf.bak"'
        )
        utils.run_command(command).return_with_print()

        print(f'Меняю параметры доступа на 700 и владельца на {config.work_user}.')
        
        # Получение UID и GID пользователя WORK_USER
        user_info = pwd.getpwnam(config.work_user) # type: ignore
        uid = user_info.pw_uid
        gid = user_info.pw_gid

        utils.run_command(
            f'docker exec wireguard bash -c "'
            f'chmod 700 /config/{user_name} && '
            f'chown -R {uid}:{gid} /config/{user_name}"'
        ).return_with_print()

        return utils.FunctionResult(status=True, description=f'Пользователь [{user_name}] успешно добавлен!').return_with_print(
            add_to_print=f'[{50*"-"}]\n')
    
    except KeyboardInterrupt:
        return utils.FunctionResult(status=False, description='Было вызвано прерывание (Ctrl+C).').return_with_print(
            error_handler=lambda: __error_exit(user_name))
    

def __remove_user_folder(user_name: str, user_state: UserState) -> utils.FunctionResult:
    """
    Удаляет папку конфигурации указанного пользователя.

    Args:
        user_name (str): Имя пользователя, чья папка конфигурации должна быть удалена.
        user_state (UserState): Статус имени пользователя (COMMENTED или UNCOMMENTED).

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    folder_name = user_name if user_state == UserState.UNCOMMENTED else f'+{user_name}'
    folder_path = os.path.join(f'{config.wireguard_folder}/config', folder_name)

    if os.path.exists(folder_path):
        try:
            utils.run_command(f'rm -r {folder_path}').return_with_print()
            return utils.FunctionResult(status=True, description=f'Папка для [{user_name}] удалена!')
        except Exception as e:
            return utils.FunctionResult(status=False, description=f'Ошибка при удалении папки для [{user_name}]: {e}')
    else:
        return utils.FunctionResult(status=False, description=f'Папка для [{user_name}] не найдена.')


def __remove_user_from_config(user_name: str) -> utils.FunctionResult:
    """
    Удаляет информацию о пользователе из конфигурационного файла WireGuard.

    Args:
        user_name (str): Имя пользователя, чьи данные должны быть удалены из конфигурационного файла.

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    filename = config.wireguard_config_filepath
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        found = False
        peer_index = -1
        for i, line in enumerate(lines):
            if line.startswith('#'):
                name = line.replace('#', '').strip()
                if name == user_name:
                    found = True
                    peer_index = i - 1
                    break

        if found and peer_index >= 0:
            del lines[peer_index:peer_index + 6]  # Удаляем 6 строк, включая [Peer]

            with open(filename, 'w', encoding='utf-8') as file:
                file.writelines(lines)

            return utils.FunctionResult(status=True,
                                  description=f'Данные для [{user_name}] были удалены из конфигурационного файла.')
        else:
            return utils.FunctionResult(status=False,
                                  description=f'Пользователь с именем [{user_name}] не найден в конфиге.')
    except IOError:
        return utils.FunctionResult(status=False,
                                  description=f'Не удалось открыть файл [{filename}] для редактирования.')


def __remove_user_from_logs(user_name: str) -> utils.FunctionResult:
    """
    Удаляет информацию о пользователе из файла логов WireGuard.

    Args:
        user_name (str): Имя пользователя, чьи данные должны быть удалены из файла логов WireGuard.

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    # Загружаем логи
    logs_data = stats.read_data_from_json(config.wireguard_log_filepath)
    
    # Удаляем пользователя из логов
    if user_name in logs_data:
        del logs_data[user_name]
        
        # Перезаписываем лог
        stats.write_data_to_json(config.wireguard_log_filepath, logs_data)
        return utils.FunctionResult(status=False,
                                    description=f'Пользователь [{user_name}] успешно удален из логов.')
    else:
        return utils.FunctionResult(status=False,
                                    description=f'Пользователь [{user_name}] отсутствует в файле логов.')
        

def __change_folder_state(user_name: str, action_type: ActionType) -> utils.FunctionResult:
    """
    Меняет состояние папки конфигурации пользователя (добавляет или удаляет префикс '+').

    Args:
        user_name (str): Имя пользователя, чья папка конфигурации должна быть перемещена.
        action_type (ActionType): Тип действия (COMMENT или UNCOMMENT), определяющий, нужно ли добавить или удалить префикс '+'.

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    old_folder = f'{config.wireguard_folder}/config/+{user_name}' if action_type == ActionType.UNCOMMENT else f'{config.wireguard_folder}/config/{user_name}'
    new_folder = f'{config.wireguard_folder}/config/+{user_name}' if action_type == ActionType.COMMENT else f'{config.wireguard_folder}/config/{user_name}'
    
    if os.path.exists(old_folder):
        try:
            utils.run_command(f'mv {old_folder} {new_folder}').return_with_print()
            action_text = 'раскомментирована' if action_type == ActionType.UNCOMMENT else 'закомментирована'
            return utils.FunctionResult(status=True, description=f'Папка для [{user_name}] успешно {action_text}.')
        except Exception as e:
            return utils.FunctionResult(status=False, description=f'Ошибка при изменении состояния папки для [{user_name}]: {e}')
    else:
        return utils.FunctionResult(status=False, description=f'Папка для [{user_name}] не найдена.')


def __comment_uncomment_in_config(user_name: str, action_type: ActionType) -> utils.FunctionResult:
    """
    Комментирует или раскомментирует блок пользователя в конфигурационном файле.

    Args:
        user_name (str): Имя пользователя, чьи данные должны быть закомментированы или раскомментированы в конфиге.
        action_type (ActionType): Тип действия (COMMENT или UNCOMMENT), определяющий, что делать с данными пользователя.

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    filename = config.wireguard_config_filepath
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        found = False
        peer_index = -1
        for i, line in enumerate(lines):
            if line.startswith('#'):
                name = line.replace('#', '').strip()
                if name == user_name:
                    found = True
                    peer_index = i - 1
                    break

        if found and peer_index >= 0:
            for i in range(peer_index, peer_index + 5):
                lines[i] = f'#{lines[i]}' if action_type == ActionType.COMMENT else lines[i][1:]

            with open(filename, 'w', encoding='utf-8') as file:
                file.writelines(lines)

            action = 'закомментированы' if action_type == ActionType.COMMENT else 'раскомментированы'
            return utils.FunctionResult(status=True, description=f'Данные для [{user_name}] были {action} в конфиге.')
        else:
            return utils.FunctionResult(status=False, description=f"Пользователь с именем [{user_name}] не найден в конфиге.")
    except IOError:
        return utils.FunctionResult(status=True, description=f'Ошибка при открытии файла [{filename}] для изменения данных [{user_name}]!')


def __modify_user(user_name: str, modify_type: UserModifyType) -> utils.FunctionResult:
    """
    Функция изменения пользователя и его данных, включая папки конфигурации и записи в конфигурационном файле.

    Args:
        user_name (str): Имя пользователя, которого хотим изменить.

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    names = os.listdir(f'{config.wireguard_folder}/config')

    print(f'\n[{50 * "-"}]')

    stripped_user_name = __strip_bad_symbols(user_name)
    if len(user_name) != len(stripped_user_name):
        return utils.FunctionResult(status=False,
                              description=f'Имя пользователя может состоять только из латинских символов и цифр!').return_with_print(
                                  add_to_print=f'[{50*"-"}]\n')

    user_name_commented = f'+{user_name}'

    if user_name in config.system_names:
        return utils.FunctionResult(status=False, description='Изменение системной папки запрещено!').return_with_print(
            add_to_print=f'[{50 * "-"}]\n'
        )

    if modify_type == UserModifyType.REMOVE:
        com_uncom_var = UserState.UNCOMMENTED if user_name in names else UserState.COMMENTED if user_name_commented in names else None
    elif modify_type == UserModifyType.COMMENT_UNCOMMENT:
        com_uncom_var = ActionType.COMMENT if user_name in names else ActionType.UNCOMMENT if user_name_commented in names else None

    if com_uncom_var is None:
        return utils.FunctionResult(status=False, description=f'Пользователя с именем [{user_name}] не существует.').return_with_print(
            add_to_print=f'[{50 * "-"}]\n'
        )
    
    if modify_type == UserModifyType.REMOVE:
        print(f'Удаляю папку конфигурации для [{user_name}]...')
        __remove_user_folder(user_name, com_uncom_var).return_with_print() # type: ignore
    elif modify_type == UserModifyType.COMMENT_UNCOMMENT:
        text = 'Комментирую' if com_uncom_var == ActionType.COMMENT else 'Раскомментирую'
        print(f'{text} папку конфигурации для [{user_name}]...')
        __change_folder_state(user_name, com_uncom_var).return_with_print() # type: ignore

    if modify_type == UserModifyType.REMOVE:
        print(f'Удаляю [{user_name}] из конфига сервера...')
        ret_val = __remove_user_from_config(user_name).return_with_print()
        __remove_user_from_logs(user_name).return_with_print()
    elif modify_type == UserModifyType.COMMENT_UNCOMMENT:
        text = 'Комментирую' if com_uncom_var == ActionType.COMMENT else 'Раскомментирую'
        print(f'{text} [{user_name}] в конфиге сервера...')
        ret_val = __comment_uncomment_in_config(user_name, com_uncom_var).return_with_print() # type: ignore

    if ret_val.status is True:
        utils.backup_config()
    else:
        return ret_val.return_with_print(add_to_print=f'[{50 * "-"}]\n')
    
    desc = f'Пользователь [{user_name}] успешно {"удалён" if modify_type == UserModifyType.REMOVE else "закомментирован" if com_uncom_var == ActionType.COMMENT else "раскомментирован"}!'
    return utils.FunctionResult(status=True, description=desc).return_with_print(add_to_print=f'[{50 * "-"}]\n')

def remove_user(user_name: str) -> utils.FunctionResult:
    """
    Удаляет пользователя и его данные из конфигурации WireGuard.

    Args:
        user_name (str): Имя пользователя, который должен быть удален.

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    return __modify_user(user_name, UserModifyType.REMOVE)


def comment_or_uncomment_user(user_name: str) -> utils.FunctionResult:
    """
    Комментирует или раскомментирует пользователя в конфигурации WireGuard.

    Args:
        user_name (str): Имя пользователя, чьи данные должны быть закомментированы или раскомментированы.

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    return __modify_user(user_name, UserModifyType.COMMENT_UNCOMMENT)


def print_user_qrcode(user_name: str) -> utils.FunctionResult:
    """
    Генерирует и выводит QR-код для пользователя WireGuard на основе его конфигурационного файла.

    Args:
        user_name (str): Имя пользователя, для которого необходимо сгенерировать QR-код.

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    print(f'\n[{50 * "-"}]')

    ret_val = check_user_exists(user_name)
    if ret_val.status is False:
        return ret_val.return_with_print(add_to_print=f'[{50 * "-"}]\n')

    if not os.path.exists(f'{config.wireguard_folder}/config/{user_name}/{user_name}.conf'):
        return utils.FunctionResult(status=False,
                              description=f"Пользователь с именем [{user_name}] был некорректно создан и не имеет конфигурационного файла!")
    
    command = (
        f'docker exec wireguard bash -c "'
        f'qrencode -t ansiutf8 < /config/{user_name}/{user_name}.conf"'
    )
    utils.run_command(command).return_with_print()

    return utils.FunctionResult(status=True, description=f"\nQrCode для [{user_name}] успешно отрисован.").return_with_print(
            add_to_print=f'[{50 * "-"}]\n'
    )

def check_user_qr_code_exists(user_name: str) -> utils.FunctionResult:
    """
    Проверяет существование QR-кода для пользователя WireGuard.

    Args:
        user_name (str): Имя пользователя для проверки.

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    ret_val = check_user_exists(user_name)
    if ret_val.status is False:
        return ret_val

    if not os.path.exists(f'{config.wireguard_folder}/config/{user_name}/{user_name}.png'):
        return utils.FunctionResult(status=False,
                              description=f"QR-кода для пользователя с именем [{user_name}] не существует.")
    
    return utils.FunctionResult(status=True, description=f"QR-код для пользователя с именем [{user_name}] найден.")


def check_user_exists(user_name: str) -> utils.FunctionResult:
    """
    Проверяет существование пользователя WireGuard.

    Args:
        user_name (str): Имя пользователя для проверки.

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    wg_db.init_db()
    row = wg_db.get_user(user_name)
    if row is None:
        return utils.FunctionResult(status=False, description=f"Пользователь с именем [{user_name}] не найден.")
    return utils.FunctionResult(status=True, description=f"Пользователь [{user_name}] найден.")


def create_zipfile(user_name: str) -> utils.FunctionResult:
    """
    Создает Zip файл для переданного пользователя, который включает в себя .conf и .png файлы.

    Args:
        user_name (str): Имя пользователя Wireguard.

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и путь к созданному Zip файлу в описание результата.
    """
    try:
        print(f'\n[{50*"-"}]')
        zip_file_path = f'{config.wireguard_folder}/config/{user_name}/{user_name}.zip'
        with zipfile.ZipFile(zip_file_path, 'w') as zipf:
            png_path = f'{config.wireguard_folder}/config/{user_name}/{user_name}.png'
            conf_path = f'{config.wireguard_folder}/config/{user_name}/{user_name}.conf'
            if os.path.exists(png_path):
                zipf.write(png_path, arcname=f'{user_name}.png')
            if os.path.exists(conf_path):
                zipf.write(conf_path, arcname=f'{user_name}.conf')
        return utils.FunctionResult(status=True, description=zip_file_path).return_with_print()
    except:
        return utils.FunctionResult(status=False, description=f'Не удалось создать Zip файл для [{user_name}].').return_with_print(add_to_print=f'[{50*"-"}]\n')


def remove_zipfile(user_name: str) -> None:
    """
    Удаляет созданный Zip файл для переданного пользователя.

    Args:
        user_name (str): Имя пользователя Wireguard.
    """
    try:
        zip_file_path = f'{config.wireguard_folder}/config/{user_name}/{user_name}.zip'
        if os.path.exists(zip_file_path):
            os.remove(zip_file_path)
            print(f'Zip файл для [{user_name}] успешно удалён.')
    except:
        print(f'Не удалось удалить Zip файл для [{user_name}].')
    finally:
        print(f'[{50*"-"}]\n')


def get_qrcode_path(user_name: str) -> utils.FunctionResult:
    """
    Возвращает путь к файлу Qr-кода для переданного пользователя Wireguard.

    Args:
        user_name (str): Имя пользователя Wireguard.

    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и путь к файлу Qr-кода в описание результата.
    """
    print(f'\n[{50*"-"}]')
    png_path = f'{config.wireguard_folder}/config/{user_name}/{user_name}.png'
    if os.path.exists(png_path):
        return utils.FunctionResult(status=True, description=png_path).return_with_print(add_to_print=f'[{50*"-"}]\n')
    return utils.FunctionResult(status=False, description=f'Не удалось найти файл Qr-кода для [{user_name}].').return_with_print(add_to_print=f'[{50*"-"}]\n')


def get_usernames() -> List[str]:
    """
    Возвращем имена конфигов всех пользователей Wireguard.

    Returns:
        list: Список имен конфигов всех пользователей Wireguard
    """
    wg_db.init_db()
    return [name for name, _ in wg_db.list_users()]


def get_active_usernames() -> List[str]:
    """
    Возвращем имена конфигов активных пользователей Wireguard.

    Returns:
        list: Список имен конфигов активных пользователей Wireguard
    """
    wg_db.init_db()
    return [name for name, commented in wg_db.list_users() if not commented]


def get_inactive_usernames() -> List[str]:
    """
    Возвращем имена конфигов отключенных пользователей Wireguard.

    Returns:
        list: Список имен конфигов отключенных пользователей Wireguard
    """
    wg_db.init_db()
    return [name for name, commented in wg_db.list_users() if commented]


def is_username_commented(user_name: str) -> bool:
    """
    Проверяет, является ли переданное имя пользователя закомментированным.

    Args:
        user_name (str): Имя пользователя Wireguard.

    Returns:
        bool: True - закомментирован, иначе False.
    """
    wg_db.init_db()
    row = wg_db.get_user(user_name)
    if row is None:
        return False
    return bool(row["commented"])


def sanitize_string(string: str) -> str:
    """
    Удаляет символы ',' и ';' из переданной строки и обрезает пробелы по краям.

    Args:
        string (str): Исходная строка.

    Returns:
        str: Очищенная строка без символов ',' и ';'.
    """
    return string.strip().translate(str.maketrans('', '', ",;"))


def add_torrent_blocking(backup: bool=True) -> utils.FunctionResult:
    """
    Обновляет конфигурацию WireGuard, заменяя базовые правила на правила с блокировкой торрентов.
    
    Args:
        backup (bool): Создать резервную копию перед изменением
    
    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    
    # Проверяем существование файла
    if not os.path.exists(config.wireguard_config_filepath):
        return utils.FunctionResult(
            status=False,
            description=f"❌ Файл {config.wireguard_config_filepath} не найден!"
        )
    
    # Создаем резервную копию
    if backup:
        backup_path = f"{config.wireguard_config_filepath}.backup"
        try:
            with open(config.wireguard_config_filepath, 'r', encoding='utf-8') as src, \
                 open(backup_path, 'w', encoding='utf-8') as dst:
                dst.write(src.read())
            print(f"✅ Резервная копия создана: {backup_path}")
        except Exception as e:
            return utils.FunctionResult(
                status=False,
                description=f"❌ Ошибка создания резервной копии: {e}"
            )
    
    # Читаем конфигурацию
    try:
        with open(config.wireguard_config_filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return utils.FunctionResult(
            status=False,
            description=f"❌ Ошибка чтения файла: {e}"
        )
    
    # Шаблоны для поиска существующих правил
    old_postup_pattern = r'PostUp\s*=\s*iptables\s+-A\s+FORWARD\s+-i\s+%i\s+-j\s+ACCEPT;\s*iptables\s+-A\s+FORWARD\s+-o\s+%i\s+-j\s+ACCEPT;\s*iptables\s+-t\s+nat\s+-A\s+POSTROUTING\s+-o\s+eth\+\s+-j\s+MASQUERADE'
    old_postdown_pattern = r'PostDown\s*=\s*iptables\s+-D\s+FORWARD\s+-i\s+%i\s+-j\s+ACCEPT;\s*iptables\s+-D\s+FORWARD\s+-o\s+%i\s+-j\s+ACCEPT;\s*iptables\s+-t\s+nat\s+-D\s+POSTROUTING\s+-o\s+eth\+\s+-j\s+MASQUERADE'
    
    # Новые правила для замены
    new_rules = f"""# Основные правила WireGuard
PostUp = iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT; iptables -t nat -A POSTROUTING -o eth+ -j MASQUERADE
# Блокировка торрентов для вашей сети {config.local_ip}0/24
PostUp = iptables -I FORWARD -s {config.local_ip}0/24 -m string --string "BitTorrent protocol" --algo bm -j DROP
PostUp = iptables -I FORWARD -s {config.local_ip}0/24 -m string --string "announce" --algo bm -j DROP
PostUp = iptables -I FORWARD -s {config.local_ip}0/24 -p tcp --dport 6881:6999 -j DROP
PostUp = iptables -I FORWARD -s {config.local_ip}0/24 -p udp --dport 6881:6999 -j DROP
# Очистка при остановке
PostDown = iptables -D FORWARD -s {config.local_ip}0/24 -m string --string "BitTorrent protocol" --algo bm -j DROP
PostDown = iptables -D FORWARD -s {config.local_ip}0/24 -m string --string "announce" --algo bm -j DROP
PostDown = iptables -D FORWARD -s {config.local_ip}0/24 -p tcp --dport 6881:6999 -j DROP
PostDown = iptables -D FORWARD -s {config.local_ip}0/24 -p udp --dport 6881:6999 -j DROP
PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT; iptables -t nat -D POSTROUTING -o eth+ -j MASQUERADE"""
    
    # Ищем совпадения
    postup_match = re.search(old_postup_pattern, content)
    postdown_match = re.search(old_postdown_pattern, content)
    
    if not postup_match:
        print("Ищем паттерн:", old_postup_pattern)
        return utils.FunctionResult(
            status=False,
            description=f"❌ Не найдены базовые правила PostUp для замены!"
        )
    
    if not postdown_match:
        return utils.FunctionResult(
            status=False,
            description=f"❌ Не найдены базовые правила PostDown для замены!"
        )
    
    print("✅ Найдены базовые правила для замены")
    
    # Определяем позицию для замены (от PostUp до PostDown включительно)
    start_pos = postup_match.start()
    end_pos = postdown_match.end()
    
    # Создаем новый контент
    new_content = content[:start_pos] + new_rules + content[end_pos:]
    
    # Сохраняем изменения
    try:
        with open(config.wireguard_config_filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"✅ Конфигурация успешно обновлена: {config.wireguard_config_filepath}")
        return utils.FunctionResult(
            status=True,
            description=f"✅ Конфигурация успешно обновлена."
        )
    except Exception as e:
        return utils.FunctionResult(
            status=False,
            description=f"❌ Ошибка записи файла: {e}"
        )

def restore_backup() -> utils.FunctionResult:
    """
    Восстанавливает конфигурацию из резервной копии.
      
    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    backup_path = f"{config.wireguard_config_filepath}.backup"
    
    if not os.path.exists(backup_path):
        return utils.FunctionResult(
            status=False,
            description=f"❌ Резервная копия {backup_path} не найдена!"
        )
    
    try:
        with open(backup_path, 'r', encoding='utf-8') as src, \
             open(config.wireguard_config_filepath, 'w', encoding='utf-8') as dst:
            dst.write(src.read())
        return utils.FunctionResult(
            status=True,
            description=f"✅ Конфигурация восстановлена из резервной копии"
        )
    except Exception as e:
        return utils.FunctionResult(
            status=False,
            description=f"❌ Ошибка восстановления: {e}"
        )

def remove_torrent_blocking(backup: bool=True) -> utils.FunctionResult:
    """
    Удаляет правила блокировки торрентов, возвращая к базовым правилам WireGuard.
    
    Args:
        backup (bool): Создать резервную копию перед изменением
    
    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    
    # Проверяем существование файла
    if not os.path.exists(config.wireguard_config_filepath):
        return utils.FunctionResult(
            status=False,
            description=f"❌ Файл {config.wireguard_config_filepath} не найден!"
        )
    
    # Создаем резервную копию
    if backup:
        backup_path = f"{config.wireguard_config_filepath}.backup"
        try:
            with open(config.wireguard_config_filepath, 'r', encoding='utf-8') as src, \
                 open(backup_path, 'w', encoding='utf-8') as dst:
                dst.write(src.read())
            print(f"✅ Резервная копия создана: {backup_path}")
        except Exception as e:
            return utils.FunctionResult(
                status=False,
                description=f"❌ Ошибка создания резервной копии: {e}"
            )
    
    # Читаем конфигурацию
    try:
        with open(config.wireguard_config_filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return utils.FunctionResult(
            status=False,
            description=f"❌ Ошибка чтения файла: {e}"
        )
    
    # Шаблон для поиска расширенных правил (от комментария до PostDown)
    extended_rules_pattern = r'# Основные правила WireGuard\s*\n.*?PostDown\s*=\s*iptables\s+-D\s+FORWARD\s+-i\s+%i\s+-j\s+ACCEPT;\s*iptables\s+-D\s+FORWARD\s+-o\s+%i\s+-j\s+ACCEPT;\s*iptables\s+-t\s+nat\s+-D\s+POSTROUTING\s+-o\s+eth\+\s+-j\s+MASQUERADE'
    
    # Базовые правила для замены
    basic_rules = """PostUp = iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT; iptables -t nat -A POSTROUTING -o eth+ -j MASQUERADE
PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT; iptables -t nat -D POSTROUTING -o eth+ -j MASQUERADE"""
    
    # Ищем расширенные правила
    match = re.search(extended_rules_pattern, content, re.DOTALL)
    
    if not match:
        return utils.FunctionResult(
            status=False,
            description=(
                f"❌ Не найдены расширенные правила для удаления!\n"
                "Возможно, в конфигурации уже базовые правила или другой формат."
            )
        )
    
    print("✅ Найдены расширенные правила для удаления")
    
    # Заменяем расширенные правила на базовые
    new_content = content[:match.start()] + basic_rules + content[match.end():]
    
    # Сохраняем изменения
    try:
        with open(config.wireguard_config_filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return utils.FunctionResult(
            status=True,
            description=f"✅ Правила блокировки торрентов успешно удалены."
        )
    except Exception as e:
        print(f"❌ Ошибка записи файла: {e}")
        return utils.FunctionResult(
            status=False,
            description=f"❌ Ошибка записи файла: {e}"
        )

def get_current_rules(html_formatting: bool = False) -> utils.FunctionResult:
    """
    Возвращает текущие правила PostUp/PostDown в конфигурации.
    
    Args:
        html_formatting (bool): Если True, возвращает результат в HTML формате
                               для отправки в Telegram.
    
    Returns:
        utils.FunctionResult: Объект, содержащий статус выполнения и описание результата.
    """
    if not os.path.exists(config.wireguard_config_filepath):
        error_msg = f"Файл {config.wireguard_config_filepath} не найден!"
        return utils.FunctionResult(
            status=False,
            description=_format_error(error_msg, html_formatting)
        )
    
    try:
        with open(config.wireguard_config_filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Ищем все правила PostUp и PostDown
        postup_rules = re.findall(r'PostUp\s*=\s*(.+)', content)
        postdown_rules = re.findall(r'PostDown\s*=\s*(.+)', content)
        
        if html_formatting:
            formatted_output = _format_rules_html(postup_rules, postdown_rules)
        else:
            formatted_output = _format_rules_text(postup_rules, postdown_rules)
            
        return utils.FunctionResult(
            status=True,
            description=formatted_output
        )
            
    except Exception as e:
        error_msg = f"Ошибка чтения файла: {e}"
        return utils.FunctionResult(
            status=False,
            description=_format_error(error_msg, html_formatting)
        )


def _format_rules_text(postup_rules: List[str], postdown_rules: List[str]) -> str:
    """Форматирует правила в текстовом формате."""
    rules = []
    
    rules.append("🔍 Текущие правила PostUp:")
    if postup_rules:
        for i, rule in enumerate(postup_rules, 1):
            rules.append(f"  {i}. {rule}")
    else:
        rules.append("  📭 Правила PostUp отсутствуют")
    
    rules.append("\n🔍 Текущие правила PostDown:")
    if postdown_rules:
        for i, rule in enumerate(postdown_rules, 1):
            rules.append(f"  {i}. {rule}")
    else:
        rules.append("  📭 Правила PostDown отсутствуют")
    
    # Добавляем статистику
    rules.append(f"\n📊 Всего правил: {len(postup_rules) + len(postdown_rules)}")
    
    return "\n".join(rules)


def _format_rules_html(postup_rules: List[str], postdown_rules: List[str]) -> str:
    """Форматирует правила в HTML формате для Telegram."""
    
    lines = []
    
    # Заголовок
    lines.append("<b>🔧 WireGuard Configuration Rules</b>\n")
    
    # PostUp правила
    lines.append("<b>🚀 PostUp Rules:</b>")
    if postup_rules:
        for i, rule in enumerate(postup_rules, 1):
            formatted_rule = _format_rule_for_telegram(rule)
            lines.append(f"  <b>{i}.</b> {formatted_rule}")
    else:
        lines.append("  <i>📭 Правила PostUp отсутствуют</i>")
    
    lines.append("")  # Пустая строка
    
    # PostDown правила
    lines.append("<b>🛑 PostDown Rules:</b>")
    if postdown_rules:
        for i, rule in enumerate(postdown_rules, 1):
            formatted_rule = _format_rule_for_telegram(rule)
            lines.append(f"  <b>{i}.</b> {formatted_rule}")
    else:
        lines.append("  <i>📭 Правила PostDown отсутствуют</i>")
    
    lines.append("")  # Пустая строка
    
    # Статистика
    total_rules = len(postup_rules) + len(postdown_rules)
    lines.append(f"<b>📊 Всего правил:</b> <u>{total_rules}</u>")
    
    return "\n".join(lines)


def _format_error(error_msg: str, html_formatting: bool) -> str:
    """Форматирует сообщение об ошибке."""
    if html_formatting:
        return f"<b>❌ Ошибка:</b> <i>{_escape_html(error_msg)}</i>"
    else:
        return f"❌ {error_msg}"


def _format_rule_for_telegram(rule: str) -> str:
    """Форматирует длинное правило для красивого отображения в Telegram."""
    
    # Экранируем HTML символы
    escaped_rule = _escape_html(rule)
    
    # Если правило короткое (до 60 символов), оставляем как есть
    if len(rule) <= 60:
        return f"<code>{escaped_rule}</code>"
    
    # Разбиваем длинное правило на части по точкам с запятой
    parts = escaped_rule.split(';')
    
    if len(parts) == 1:
        # Если нет точек с запятой, разбиваем по логическим частям
        return _format_single_long_rule(escaped_rule)
    
    # Форматируем каждую часть на отдельной строке
    formatted_parts = []
    for i, part in enumerate(parts):
        part = part.strip()
        if part:
            if i == 0:
                # Первая часть
                formatted_parts.append(f"<code>{part}</code>")
            else:
                # Остальные части с отступом
                formatted_parts.append(f"    <code>{part}</code>")
    
    return ";\n".join(formatted_parts)


def _format_single_long_rule(rule: str) -> str:
    """Форматирует одиночное длинное правило без точек с запятой."""
    
    # Ищем ключевые параметры для переноса
    keywords = [
        '-A ', '-I ', '-D ', '-s ', '-d ', '-p ',
        '--dport ', '--sport ', '--string ', '-m ', '-j ', '-t '
    ]
    
    # Если правило содержит несколько ключевых параметров, разбиваем его
    parts = []
    current_part = ""
    words = rule.split()
    
    for word in words:
        if current_part and any(word.startswith(kw.strip()) for kw in keywords) and len(current_part) > 30:
            parts.append(current_part.strip())
            current_part = word
        else:
            current_part += " " + word if current_part else word
    
    if current_part:
        parts.append(current_part.strip())
    
    if len(parts) <= 1:
        # Если не удалось разбить, просто оборачиваем в code
        return f"<code>{rule}</code>"
    
    # Форматируем части
    formatted_parts = []
    for i, part in enumerate(parts):
        if i == 0:
            formatted_parts.append(f"<code>{part}</code>")
        else:
            formatted_parts.append(f"    <code>{part}</code>")
    
    return " \\\n".join(formatted_parts)


def _escape_html(text: str) -> str:
    """Экранирует HTML символы для Telegram."""
    return (text.replace('&', '&amp;')
               .replace('<', '&lt;')
               .replace('>', '&gt;'))
    

def check_torrent_blocking_status() -> Literal['unknown', 'enabled', 'disabled']:
    """
    Проверяет, включена ли блокировка торрентов в конфигурации.
    
    Returns:
        str: "enabled", "disabled", или "unknown"
    """
    if not os.path.exists(config.wireguard_config_filepath):
        print(f"❌ Файл {config.wireguard_config_filepath} не найден!")
        return "unknown"
    
    try:
        with open(config.wireguard_config_filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Ищем признаки блокировки торрентов
        torrent_blocking_patterns = [
            r'BitTorrent protocol',
            r'announce',
            r'--dport 6881:6999',
            r'# Блокировка торрентов'
        ]
        
        for pattern in torrent_blocking_patterns:
            if re.search(pattern, content):
                return "enabled"
        
        return "disabled"
        
    except Exception as e:
        print(f"❌ Ошибка чтения файла: {e}")
        return "unknown"
