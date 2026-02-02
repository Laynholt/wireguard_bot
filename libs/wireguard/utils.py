import os
import logging
import asyncio
import subprocess

from .types import FunctionResult
from ..core import config
from . import stats


logger = logging.getLogger(__name__)


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
    Создает резервную копию конфигурационного файла WireGuard и базы wg_users.db
    """
    try:
        os.makedirs(f'{config.wireguard_folder}/config/wg_confs_backup', exist_ok=True)
        run_command(
            f'cp {config.wireguard_config_filepath}'
            f' {config.wireguard_folder}/config/wg_confs_backup/wg0.conf'
        ).return_with_print()
        # Бэкап базы пользователей
        db_src = f'{config.wireguard_folder}/config/wg_users.db'
        db_dst = f'{config.wireguard_folder}/config/wg_confs_backup/wg_users.db'
        if os.path.exists(db_src):
            run_command(f'cp {db_src} {db_dst}').return_with_print()
            print('Резервная копия базы пользователей создана.')
        else:
            print('База пользователей не найдена, пропускаю её бэкап.')
        print('Резервная копия конфига создана.')
    except Exception as e:
        print(f'Ошибка при создании резервной копии: {e}')


def log_wireguard_status():
    """
    Накопительно сохраняет статистику WireGuard в БД.
    """
    stats.accumulate_wireguard_stats(
        conf_file_path=config.wireguard_config_filepath,
        sort_by=stats.SortBy.TRANSFER_SENT
    )
    print(f"[+] Логи Wireguard успешно обновлены и сохранены в базе.")

def log_and_restart_wireguard() -> bool:
    """
    Сначала выполняет запись лога с помощью log_wireguard_status(),
    затем перезагружает WireGuard через команду 'docker compose restart wireguard'.
    """
    log_wireguard_status()  # Записываем лог с выводом show_info.py
    print('Перезагружаю Wireguard...')
    run_command(f'docker compose -f {config.wireguard_folder}/docker-compose.yml restart wireguard').return_with_print()  # Перезагрузка WireGuard
    return True

async def async_restart_wireguard() -> bool:
    """Асинхронная обертка для синхронной операции перезагрузки WireGuard.
    
    Запускает блокирующую операцию в отдельном потоке, чтобы не блокировать event loop.
    
    Returns:
        bool: Результат операции перезагрузки
            - True: перезагрузка успешно выполнена
            - False: произошла ошибка при перезагрузке
            
    Raises:
        Exception: Любые исключения из wireguard_utils.log_and_restart_wireguard 
            будут перехвачены и залогированы, но не проброшены выше
            
    Notes:
        - Использует дефолтный ThreadPoolExecutor
        - Является internal-функцией (не предназначена для прямого вызова)
    """
    loop = asyncio.get_running_loop()   
    try:
        return await loop.run_in_executor(
            None,
            log_and_restart_wireguard
        )
    except Exception as e:
        logger.error(f"Ошибка перезагрузки: {str(e)}")
        return False
