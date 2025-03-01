from doctest import FAIL_FAST
from enum import Enum
from tkinter.font import BOLD


class BotCommands(str, Enum):
    START = "start"
    HELP = "help"
    MENU = "menu"
    CANCEL = "cancel"
    UNKNOWN = "unknown"
    
    ADD_USER = "add_user"
    REMOVE_USER = "remove_user"
    COM_UNCOM_USER = "com_uncom_user"
    SHOW_USERS_STATE = "show_users_state"
    
    BIND_USER = "bind_user"
    UNBIND_USER = "unbind_user"
    UNBIND_TELEGRAM_ID = "unbind_telegram_id"
    GET_USERS_BY_ID = "get_users_by_id"
    SHOW_ALL_BINDINGS = "show_all_bindings"
    
    BAN_TELEGRAM_USER = "ban_telegram_user"
    UNBAN_TELEGRAM_USER = "unban_telegram_user"
    REMOVE_TELEGRAM_USER = "remove_telegram_user"
    
    GET_CONFIG = "get_config"
    GET_QRCODE = "get_qrcode"
    REQUEST_NEW_CONFIG = "request_new_config"
    SEND_CONFIG = "send_config"
    
    GET_TELEGRAM_ID = "get_telegram_id"
    GET_TELEGRAM_USERS = "get_telegram_users"
    SEND_MESSAGE = "send_message"
    
    GET_MY_STATS = "get_my_stats"
    GET_USER_STATS = "get_user_stats"
    GET_ALL_STATS = "get_all_stats"
    
    RELOAD_WG_SERVER = "reload_wg_server"
    


from .base import BaseCommand

from .start             import StartCommand
from .help              import HelpCommand
from .menu              import MenuCommand
from .cancel            import CancelCommand

from .add               import AddWireguardUserCommand
from .rem               import RemoveWireguardUserCommand
from .com               import CommentWireguardUserCommand
from .show_users_state  import ShowWireguardUsersStateCommand

from .bind              import BindWireguardUserCommand
from .unbind            import UnbindWireguardUserCommand
from .unbind_tid        import UnbindTelegramUserCommand
from .get_users_by_tid  import GetWireguardUsersByTIdCommand
from .show_all_bindings import ShowAllBindingsCommand

from .ban               import BanTelegramUserCommand
from .unban             import UnbanTelegramUserCommand
from .rem_tg_user       import RemoveTelegramUserCommand

from .get_config        import GetWireguardConfigOrQrcodeCommand
from .req_new_config    import RequestNewConfigCommand
from .send_config       import SendConfigCommand

from .get_tid           import GetTelegramIdCommand
from .get_tg_users      import GetTelegramUsersCommand
from .send_message      import SendMessageCommand

from .get_stats_user    import GetWireguardUserStatsCommand
from .get_stats_all     import GetAllWireguardUsersStatsCommand

from .reload_wg         import ReloadWireguardServerCommand

from .unknown           import UnknownCommand


from typing import Dict
from asyncio import Semaphore
from libs.core.config import Config
from libs.telegram.database import UserDatabase
from libs.telegram.types import TelegramId


class BotCommandHandler:
    def __init__(
        self,
        config: Config,
        database: UserDatabase,
        semaphore: Semaphore,
        telegram_user_ids_cache: set[TelegramId] 
    ) -> None:
        """
        Инициализация обработчика команд.

        Args:
            config (Config): Конфигурация бота.
            database (UserDatabase): Объект базы данных.
            semaphore (Semaphore): Семафор для ограничения одновременных запросов.
            telegram_user_ids_cache (set[TelegramId]): Кеш Telegram ID пользователей.
        """
        self.__command_wrapper: Dict[BotCommands, BaseCommand] = {}  # Словарь для хранения команд.
        self.__init_commands(config, database, semaphore, telegram_user_ids_cache)

    def command(self, bot_command: BotCommands) -> BaseCommand:
        """
        Получает обработчик команды по её идентификатору.

        Args:
            bot_command (BotCommands): Команда бота.

        Returns:
            BaseCommand: Обработчик команды.
        """
        if bot_command not in self.__command_wrapper:    
            return self.__command_wrapper[BotCommands.UNKNOWN]
        return self.__command_wrapper[bot_command]
    
    def __init_commands(
        self,
        config: Config,
        database: UserDatabase,
        semaphore: Semaphore,
        telegram_user_ids_cache: set[TelegramId]
    ):
        """
        Инициализация всех команд бота.
        """
        # Базовые команды
        self.__command_wrapper[BotCommands.START] = StartCommand(
            database,
            config.telegram_admin_ids,
            telegram_user_ids_cache
        )
        self.__command_wrapper[BotCommands.HELP] = HelpCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommands.MENU] = MenuCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommands.CANCEL] = CancelCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommands.UNKNOWN] = UnknownCommand(
            database,
            config.telegram_admin_ids
        )
        
        # Команды управления пользователями WireGuard
        self.__command_wrapper[BotCommands.ADD_USER] = AddWireguardUserCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommands.REMOVE_USER] = RemoveWireguardUserCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommands.COM_UNCOM_USER] = CommentWireguardUserCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommands.SHOW_USERS_STATE] = ShowWireguardUsersStateCommand(
            database,
            config.telegram_admin_ids,
            semaphore
        )
        
        # Команды привязки и отвязки пользователей
        self.__command_wrapper[BotCommands.BIND_USER] = BindWireguardUserCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommands.UNBIND_USER] = UnbindWireguardUserCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommands.UNBIND_TELEGRAM_ID] = UnbindTelegramUserCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommands.GET_USERS_BY_ID] = GetWireguardUsersByTIdCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommands.SHOW_ALL_BINDINGS] = ShowAllBindingsCommand(
            database,
            config.telegram_admin_ids,
            semaphore
        )
        
        # Команды управления пользователями Telegram
        self.__command_wrapper[BotCommands.BAN_TELEGRAM_USER] = BanTelegramUserCommand(
            database,
            config.telegram_admin_ids,
            telegram_user_ids_cache
        )
        self.__command_wrapper[BotCommands.UNBAN_TELEGRAM_USER] = UnbanTelegramUserCommand(
            database,
            config.telegram_admin_ids,
            telegram_user_ids_cache
        )
        self.__command_wrapper[BotCommands.REMOVE_TELEGRAM_USER] = RemoveTelegramUserCommand(
            database,
            config.telegram_admin_ids,
            telegram_user_ids_cache,
            config.wireguard_log_filepath
        )
        
        # Команды управления конфигурацией WireGuard
        self.__command_wrapper[BotCommands.GET_CONFIG] = GetWireguardConfigOrQrcodeCommand(
            database,
            config.telegram_admin_ids,
            return_config=True
        )
        self.__command_wrapper[BotCommands.GET_QRCODE] = GetWireguardConfigOrQrcodeCommand(
            database,
            config.telegram_admin_ids,
            return_config=False
        )
        self.__command_wrapper[BotCommands.REQUEST_NEW_CONFIG] = RequestNewConfigCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommands.SEND_CONFIG] = SendConfigCommand(
            database,
            config.telegram_admin_ids
        )
        
        # Команды работы с Telegram ID
        self.__command_wrapper[BotCommands.GET_TELEGRAM_ID] = GetTelegramIdCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommands.GET_TELEGRAM_USERS] = GetTelegramUsersCommand(
            database,
            config.telegram_admin_ids,
            semaphore
        )
        self.__command_wrapper[BotCommands.SEND_MESSAGE] = SendMessageCommand(
            database,
            config.telegram_admin_ids,
            telegram_user_ids_cache
        )
        
        # Команды получения статистики WireGuard
        self.__command_wrapper[BotCommands.GET_MY_STATS] = GetWireguardUserStatsCommand(
            database,
            config.telegram_admin_ids,
            config.wireguard_config_filepath,
            config.wireguard_log_filepath,
            return_own_stats=True
        )
        self.__command_wrapper[BotCommands.GET_USER_STATS] = GetWireguardUserStatsCommand(
            database,
            config.telegram_admin_ids,
            config.wireguard_config_filepath,
            config.wireguard_log_filepath,
            return_own_stats=False
        )
        self.__command_wrapper[BotCommands.GET_ALL_STATS] = GetAllWireguardUsersStatsCommand(
            database,
            config.telegram_admin_ids,
            semaphore,
            config.wireguard_config_filepath,
            config.wireguard_log_filepath
        )
        
        # Команда перезапуска сервера WireGuard
        self.__command_wrapper[BotCommands.RELOAD_WG_SERVER] = ReloadWireguardServerCommand(
            database,
            config.telegram_admin_ids
        )
