from enum import Enum

class BotCommand(str, Enum):
    def __new__(cls, command: str, pretty_text: str) -> "BotCommand":
        obj = str.__new__(cls, command)
        obj._value_ = command
        return obj

    def __init__(self, command: str, pretty_text: str) -> None:
        self.pretty_text: str = pretty_text

    # Базовые команды
    START = ("start", "Старт")
    HELP = ("help", "Помощь")
    MENU = ("menu", "Меню")
    CANCEL = ("cancel", "Отмена")
    UNKNOWN = ("unknown", "Неизвестная команда")

    # Управление пользователями WireGuard
    ADD_USER = ("add_user", "Добавить пользователя")
    REMOVE_USER = ("remove_user", "Удалить пользователя")
    COM_UNCOM_USER = ("com_uncom_user", "Закомментировать/раскомментировать")
    SHOW_USERS_STATE = ("show_users_state", "Состояние пользователей")

    # Привязка пользователей WireGuard
    BIND_USER = ("bind_user", "Привязать пользователя")
    UNBIND_USER = ("unbind_user", "Отвязать пользователя")
    UNBIND_TELEGRAM_ID = ("unbind_telegram_id", "Отвязать Telegram ID")
    GET_USERS_BY_ID = ("get_users_by_id", "Пользователи по ID")
    SHOW_ALL_BINDINGS = ("show_all_bindings", "Показать привязки")

    # Управление Telegram-пользователями
    BAN_TELEGRAM_USER = ("ban_telegram_user", "Забанить пользователя")
    UNBAN_TELEGRAM_USER = ("unban_telegram_user", "Разбанить пользователя")
    REMOVE_TELEGRAM_USER = ("remove_telegram_user", "Удалить Telegram пользователя")

    # Конфигурационные команды WireGuard
    GET_CONFIG = ("get_config", "Получить конфиг")
    GET_QRCODE = ("get_qrcode", "Получить QR-код")
    REQUEST_NEW_CONFIG = ("request_new_config", "Запрос нового конфига")
    SEND_CONFIG = ("send_config", "Отправить конфиг")

    # Информация, связанная с Telegram
    GET_TELEGRAM_ID = ("get_telegram_id", "Получить Telegram ID")
    GET_TELEGRAM_USERS = ("get_telegram_users", "Показать пользователей Telegram")
    SEND_MESSAGE = ("send_message", "Рассылка сообщения")

    # Статистика WireGuard
    GET_MY_STATS = ("get_my_stats", "Моя статистика")
    GET_USER_STATS = ("get_user_stats", "Статистика пользователя")
    GET_ALL_STATS = ("get_all_stats", "Вся статистика")

    # Дополнительные команды
    RELOAD_WG_SERVER = ("reload_wg_server", "Перезагрузить сервер")
    


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
        self.__command_wrapper: Dict[BotCommand, BaseCommand] = {}  # Словарь для хранения команд.
        self.__init_commands(config, database, semaphore, telegram_user_ids_cache)

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
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommand.CANCEL] = CancelCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommand.UNKNOWN] = UnknownCommand(
            database,
            config.telegram_admin_ids
        )
        
        # Команды управления пользователями WireGuard
        self.__command_wrapper[BotCommand.ADD_USER] = AddWireguardUserCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommand.REMOVE_USER] = RemoveWireguardUserCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommand.COM_UNCOM_USER] = CommentWireguardUserCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommand.SHOW_USERS_STATE] = ShowWireguardUsersStateCommand(
            database,
            config.telegram_admin_ids,
            semaphore
        )
        
        # Команды привязки и отвязки пользователей
        self.__command_wrapper[BotCommand.BIND_USER] = BindWireguardUserCommand(
            database,
            config.telegram_admin_ids,
            telegram_user_ids_cache
        )
        self.__command_wrapper[BotCommand.UNBIND_USER] = UnbindWireguardUserCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommand.UNBIND_TELEGRAM_ID] = UnbindTelegramUserCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommand.GET_USERS_BY_ID] = GetWireguardUsersByTIdCommand(
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommand.SHOW_ALL_BINDINGS] = ShowAllBindingsCommand(
            database,
            config.telegram_admin_ids,
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
            database,
            config.telegram_admin_ids
        )
        self.__command_wrapper[BotCommand.GET_TELEGRAM_USERS] = GetTelegramUsersCommand(
            database,
            config.telegram_admin_ids,
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
            config.telegram_admin_ids,
            config.wireguard_config_filepath,
            config.wireguard_log_filepath,
            return_own_stats=True
        )
        self.__command_wrapper[BotCommand.GET_USER_STATS] = GetWireguardUserStatsCommand(
            database,
            config.telegram_admin_ids,
            config.wireguard_config_filepath,
            config.wireguard_log_filepath,
            return_own_stats=False
        )
        self.__command_wrapper[BotCommand.GET_ALL_STATS] = GetAllWireguardUsersStatsCommand(
            database,
            config.telegram_admin_ids,
            semaphore,
            config.wireguard_config_filepath,
            config.wireguard_log_filepath
        )
        
        # Команда перезапуска сервера WireGuard
        self.__command_wrapper[BotCommand.RELOAD_WG_SERVER] = ReloadWireguardServerCommand(
            database,
            config.telegram_admin_ids
        )
