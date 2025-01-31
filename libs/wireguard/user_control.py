import os
import re
import pwd
from typing import List
import zipfile
import ipaddress
from enum import Enum

from . import config
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
    if config.is_dns_server_in_docker:
        ret_val = utils.run_command(
            "docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' " + config.dns_server_name
        )
        if not ret_val.status:
            ret_val.return_with_print()
            return f'{config.local_ip}1'
        return ret_val.description.strip()

    try:
        ipaddress.ip_address(config.dns_server_name)
        return config.dns_server_name
    except ValueError:
        return f'{config.local_ip}1'


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
                    f'ListenPort = 51820\n'
                    f'DNS = {__get_dsn_server_ip()}\n\n'
                    f'[Peer]\n'
                    f'PublicKey = {server_public_key}\n'
                    f'PresharedKey = {user_preshared_key}\n'
                    f'Endpoint = {config.server_ip}:{config.server_port}\n'
                    f'AllowedIPs = 0.0.0.0/0\n'
                    f'PersistentKeepalive = 30\n'
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
    names = os.listdir(f'{config.wireguard_folder}/config')
    
    stripped_user_name = __strip_bad_symbols(user_name)
    if len(user_name) != len(stripped_user_name):
        return utils.FunctionResult(status=False, description=f'Имя пользователя может состоять только из латинских символов и цифр!')
    
    user_name_commented = f'+{user_name}'

    if user_name in config.system_names:
        return utils.FunctionResult(status=False, description=f'Имя пользователя [{user_name}] совпадает с названием системной папки!')

    if user_name not in names and user_name_commented not in names:
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
    return [__strip_bad_symbols(user_name) for user_name in os.listdir(f'{config.wireguard_folder}/config') if user_name not in config.system_names]


def get_active_usernames() -> List[str]:
    """
    Возвращем имена конфигов активных пользователей Wireguard.

    Returns:
        list: Список имен конфигов активных пользователей Wireguard
    """
    return [user_name for user_name in os.listdir(f'{config.wireguard_folder}/config') if user_name not in config.system_names and '+' not in user_name]


def get_inactive_usernames() -> List[str]:
    """
    Возвращем имена конфигов отключенных пользователей Wireguard.

    Returns:
        list: Список имен конфигов отключенных пользователей Wireguard
    """
    return [user_name[1:] for user_name in os.listdir(f'{config.wireguard_folder}/config') if user_name not in config.system_names and '+' in user_name]


def is_username_commented(user_name: str) -> bool:
    """
    Проверяет, является ли переданное имя пользователя закомментированным.
    
    !Важно!
    Данная функция не проверяет существования пользователя.

    Args:
        user_name (str): Имя пользователя Wireguard.

    Returns:
        bool: True - закомментирован, иначе False.
    """
    return user_name in get_inactive_usernames()