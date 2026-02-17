import os
import logging
import asyncio
import subprocess
import shlex
import shutil
from typing import Sequence, Union, Optional

from .types import FunctionResult
from ..core import config
from . import stats


logger = logging.getLogger(__name__)


def run_command(
    command: Union[str, Sequence[str]],
    timeout_sec: int = 60,
    stdin_data: Optional[str] = None,
) -> FunctionResult:
    """
    Выполняет команду и проверяет, успешно ли она завершилась.

    Args:
        command (Union[str, Sequence[str]]): Команда для выполнения.
        timeout_sec (int): Таймаут выполнения в секундах.
        stdin_data (Optional[str]): Текст для передачи в stdin процесса.

    Returns:
        FunctionResult: Результат выполнения команды.
    """
    try:
        args = shlex.split(command) if isinstance(command, str) else list(command)
        result = subprocess.run(
            args,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            input=stdin_data,
        )
        return FunctionResult(status=True, description=f'{result.stdout}')
    except subprocess.CalledProcessError as e:
        return FunctionResult(status=False, description=f'{e.stderr or e.stdout}')
    except subprocess.TimeoutExpired as e:
        return FunctionResult(status=False, description=f'Команда превысила таймаут {timeout_sec}s: {e}')
    except FileNotFoundError as e:
        return FunctionResult(status=False, description=f'Не найден исполняемый файл: {e}')


def backup_config() -> None:
    """
    Создает резервную копию конфигурационного файла WireGuard и базы wg_users.db
    """
    try:
        backup_dir = os.path.join(config.wireguard_folder, "config", "wg_confs_backup")
        os.makedirs(backup_dir, exist_ok=True)

        cfg_dst = os.path.join(backup_dir, "wg0.conf")
        shutil.copy2(config.wireguard_config_filepath, cfg_dst)

        # Бэкап базы пользователей
        db_src = os.path.join(config.wireguard_folder, "config", "wg_users.db")
        db_dst = os.path.join(backup_dir, "wg_users.db")
        if os.path.exists(db_src):
            shutil.copy2(db_src, db_dst)
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
    run_command([
        "docker", "compose",
        "-f", os.path.join(config.wireguard_folder, "docker-compose.yml"),
        "restart", "wireguard",
    ]).return_with_print()  # Перезагрузка WireGuard
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
