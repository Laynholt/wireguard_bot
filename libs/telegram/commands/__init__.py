from .commands import BotCommand

from .base import BaseCommand, ContextDataKeys

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
        self.__command_wrapper: Dict[BotCommand, BaseCommand] = {}  # Словарь для хранения команд.
        self.__init_commands(
            config, database, semaphore, telegram_user_ids_cache
        )

    def command(self, bot_command: BotCommand) -> BaseCommand:
        """
        Получает обработчик команды по её идентификатору.

        Args:
            bot_command (BotCommands): Команда бота.

        Returns:
            BaseCommand: Обработчик команды.
        """
        if bot_command not in self.__command_wrapper:    
            return self.__command_wrapper[BotCommand.UNKNOWN]
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
        self.__command_wrapper[BotCommand.START] = StartCommand(
            database,
            config.telegram_admin_ids,
            telegram_user_ids_cache
        )
        self.__command_wrapper[BotCommand.HELP] = HelpCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommand.MENU] = MenuCommand(
            database
        )
        self.__command_wrapper[BotCommand.CANCEL] = CancelCommand(
            database
        )
        self.__command_wrapper[BotCommand.UNKNOWN] = UnknownCommand(
            database
        )
        
        # Команды управления пользователями WireGuard
        self.__command_wrapper[BotCommand.ADD_USER] = AddWireguardUserCommand(
            database
        )
        self.__command_wrapper[BotCommand.REMOVE_USER] = RemoveWireguardUserCommand(
            database
        )
        self.__command_wrapper[BotCommand.COM_UNCOM_USER] = CommentWireguardUserCommand(
            database
        )
        self.__command_wrapper[BotCommand.SHOW_USERS_STATE] = ShowWireguardUsersStateCommand(
            database,
            semaphore
        )
        
        # Команды привязки и отвязки пользователей
        self.__command_wrapper[BotCommand.BIND_USER] = BindWireguardUserCommand(
            database,
            telegram_user_ids_cache
        )
        self.__command_wrapper[BotCommand.UNBIND_USER] = UnbindWireguardUserCommand(
            database
        )
        self.__command_wrapper[BotCommand.UNBIND_TELEGRAM_ID] = UnbindTelegramUserCommand(
            database
        )
        self.__command_wrapper[BotCommand.GET_USERS_BY_ID] = GetWireguardUsersByTIdCommand(
            database
        )
        self.__command_wrapper[BotCommand.SHOW_ALL_BINDINGS] = ShowAllBindingsCommand(
            database,
            semaphore
        )
        
        # Команды управления пользователями Telegram
        self.__command_wrapper[BotCommand.BAN_TELEGRAM_USER] = BanTelegramUserCommand(
            database,
            config.telegram_admin_ids,
            telegram_user_ids_cache
        )
        self.__command_wrapper[BotCommand.UNBAN_TELEGRAM_USER] = UnbanTelegramUserCommand(
            database,
            config.telegram_admin_ids,
            telegram_user_ids_cache
        )
        self.__command_wrapper[BotCommand.REMOVE_TELEGRAM_USER] = RemoveTelegramUserCommand(
            database,
            config.telegram_admin_ids,
            telegram_user_ids_cache
        )
        
        # Команды управления конфигурацией WireGuard
        self.__command_wrapper[BotCommand.GET_CONFIG] = GetWireguardConfigOrQrcodeCommand(
            database,
            config.telegram_admin_ids,
            return_config=True
        )
        self.__command_wrapper[BotCommand.GET_QRCODE] = GetWireguardConfigOrQrcodeCommand(
            database,
            config.telegram_admin_ids,
            return_config=False
        )
        self.__command_wrapper[BotCommand.REQUEST_NEW_CONFIG] = RequestNewConfigCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommand.SEND_CONFIG] = SendConfigCommand(
            database,
            config.telegram_admin_ids
        )
        
        # Команды работы с Telegram ID
        self.__command_wrapper[BotCommand.GET_TELEGRAM_ID] = GetTelegramIdCommand(
            database
        )
        self.__command_wrapper[BotCommand.GET_TELEGRAM_USERS] = GetTelegramUsersCommand(
            database,
            semaphore
        )
        self.__command_wrapper[BotCommand.SEND_MESSAGE] = SendMessageCommand(
            database,
            config.telegram_admin_ids,
            telegram_user_ids_cache
        )
        
        # Команды получения статистики WireGuard
        self.__command_wrapper[BotCommand.GET_MY_STATS] = GetWireguardUserStatsCommand(
            database,
            config.wireguard_config_filepath,
            config.wireguard_log_filepath,
            return_own_stats=True
        )
        self.__command_wrapper[BotCommand.GET_USER_STATS] = GetWireguardUserStatsCommand(
            database,
            config.wireguard_config_filepath,
            config.wireguard_log_filepath,
            return_own_stats=False
        )
        self.__command_wrapper[BotCommand.GET_ALL_STATS] = GetAllWireguardUsersStatsCommand(
            database,
            semaphore,
            config.wireguard_config_filepath,
            config.wireguard_log_filepath
        )
        
        # Команда перезапуска сервера WireGuard
        self.__command_wrapper[BotCommand.RELOAD_WG_SERVER] = ReloadWireguardServerCommand(
            database
        )
