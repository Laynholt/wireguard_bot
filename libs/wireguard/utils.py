import os
import subprocess
from typing import Callable, Optional

from . import config
from . import stats

class FunctionResult:
    """
    Класс для представления результата выполнения операций над пользователями WireGuard.

    Attributes:
        status (bool): Статус выполнения операции (успешно или нет).
        description (str): Поясняющая строка, содержащая информацию об ошибке или успехе операции.
    """
    def __init__(self, status: bool, description: str) -> None:
        self.status = status 
        self.description = description

    def return_with_print(self, error_handler: Optional[Callable[[], None]] = None, add_to_print: str = '') -> 'FunctionResult':
        """
        Возвращает результат выполнения функции с выводом описания результата.

        Args:
            error_handler (callable): Функция для обработки ошибок, которую нужно вызвать в случае ошибки.
            add_to_print (str): Добавляет строку вывода после description.

        Returns:
            FunctionResult: Результат выполнения функции.
        """
        if self.description:
            prefix = 'Ошибка! ' if self.status is False else ''
            print(f'{prefix}{self.description}')
        
        if add_to_print:
            print(add_to_print)

        if error_handler and self.status is False:
            error_handler()  # Вызываем переданную функцию без дополнительных аргументов здесь

        return self


def run_command(command: str) -> FunctionResult:
    """
    Выполняет команду в системной оболочке и проверяет, успешно ли она завершилась.

    Args:
        command (str): Команда для выполнения.

    Returns:
        bool: True, если команда успешно выполнена, иначе False.
    """
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        return FunctionResult(status=True, description=f'{result.stdout}')
    except subprocess.CalledProcessError as e:
        return FunctionResult(status=False, description=f'{e.stderr}')


def backup_config() -> None:
    """
    Создает резервную копию конфигурационного файла WireGuard
    """
    try:
        os.makedirs(f'{config.wireguard_folder}/config/wg_confs_backup', exist_ok=True)
        run_command(
            f'cp {config.wireguard_config_filepath}'
            f' {config.wireguard_folder}/config/wg_confs_backup/wg0.conf'
        ).return_with_print()
        print('Резервная копия конфига создана.')
    except Exception as e:
        print(f'Ошибка при создании резервной копии: {e}')


def setup_logs_directory():
    """
    Проверяет, существует ли папка 'logs' в директории 'config'.
    Если папка не существует, она создается.
    """
    log_dir = os.path.dirname(config.wireguard_log_filepath)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)  # Создаем папку, если её нет
        print(f'Папка {log_dir} создана.')
    else:
        print(f'Папка {log_dir} уже существует.')


def log_wireguard_status():
    """
    Накопительно сохраняет статистику WireGuard в JSON-файл.

    Функция:
      1. Убеждается, что папка для логов (logs) существует.
      2. Формирует путь к файлу конфигурации (wg0.conf).
      3. Формирует путь к JSON-файлу для накопительной статистики (stats.json).
      4. Вызывает функцию `accumulate_wireguard_stats`, которая:
         - Читает прежние данные из stats.json.
         - Парсит новый вывод WireGuard (docker exec wireguard wg show wg0).
         - Суммирует трафик (transfer_received / transfer_sent).
         - Обновляет поле latest_handshake.
         - Перезаписывает обновлённые данные в stats.json.

    Returns:
        None
    """
    setup_logs_directory()  # Убедиться, что папка logs существует
    
    wireguard_stats = stats.accumulate_wireguard_stats(
        conf_file_path=config.wireguard_config_filepath,
        json_file_path=config.wireguard_log_filepath,
        sort_by=stats.SortBy.TRANSFER_SENT
    )
    
    stats.write_data_to_json(config.wireguard_log_filepath, wireguard_stats)
    print(f"[+] Логи Wireguard успешно обновлены и сохранены в [{config.wireguard_log_filepath}]")

def log_and_restart_wireguard():
    """
    Сначала выполняет запись лога с помощью log_wireguard_status(),
    затем перезагружает WireGuard через команду 'docker compose restart wireguard'.
    """
    log_wireguard_status()  # Записываем лог с выводом show_info.py
    print('Перезагружаю Wireguard...')
    run_command(f'docker compose -f {config.wireguard_folder}/docker-compose.yml restart wireguard').return_with_print()  # Перезагрузка WireGuard