from enum import Enum

class BotCommands(str, Enum):
    START = "start"
    HELP = "help"
    MENU = "menu"
    CANCEL = "cancel"
    
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
    SHOW_BANNED_TELEGRAM_USER = "show_banned_telegram_user"
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