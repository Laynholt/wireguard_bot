from enum import Enum

class BotCommand(str, Enum):
    def __new__(cls, command: str, pretty_text: str) -> "BotCommand":
        obj = str.__new__(cls, command)
        obj._value_ = command
        return obj

    def __init__(self, command: str, pretty_text: str) -> None:
        self.pretty_text: str = pretty_text
    
    @classmethod
    def from_command(cls, command_str: str) -> "BotCommand":
        """
        Преобразует входящую строку (например, "/start" или "start")
        в объект BotCommand. Если команда неизвестна, возвращает BotCommand.UNKNOWN.
        """
        command_str = command_str.lstrip('/')
        for cmd in cls:
            if cmd.value == command_str:
                return cmd
        return cls.UNKNOWN


    # Базовые команды
    START = ("start", "Старт")
    HELP = ("help", "Помощь")
    MENU = ("menu", "Меню")
    CANCEL = ("cancel", "Отмена")
    UNKNOWN = ("unknown", "Неизвестная команда")

    # Управление пользователями WireGuard
    ADD_USER = ("add_user", "Добавить пользователя")
    REMOVE_USER = ("remove_user", "Удалить пользователя")
    COM_UNCOM_USER = ("com_uncom_user", "Комментировать пользователя")
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