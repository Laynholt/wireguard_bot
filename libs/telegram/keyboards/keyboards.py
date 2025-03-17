from libs.telegram.commands.commands import BotCommand
from libs.telegram.keyboards import keys
from libs.telegram.keyboards.menu_keyboard import *


# Подменю "Действия с пользователями WireGuard"
WIREGUARD_ACTIONS_KEYBOARD = Keyboard(
    title="⚙️ Действия с пользователями WireGuard",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.ADD_USER.pretty_text,),
            (BotCommand.REMOVE_USER.pretty_text,),
            (BotCommand.COM_UNCOM_USER.pretty_text,),
            (BotCommand.SHOW_USERS_STATE.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)

# Подменю "Привязка пользователей WireGuard"
WIREGUARD_BINDINGS_KEYBOARD = Keyboard(
    title="🔗 Привязка пользователей WireGuard",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.BIND_USER.pretty_text,),
            (BotCommand.UNBIND_USER.pretty_text,),
            (BotCommand.UNBIND_TELEGRAM_ID.pretty_text,),
            (BotCommand.GET_USERS_BY_ID.pretty_text,),
            (BotCommand.SHOW_ALL_BINDINGS.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)

# Подменю "Действия с пользователями Telegram"
TELEGRAM_ACTIONS_KEYBOARD = Keyboard(
    title="👤 Действия с пользователями Telegram",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.BAN_TELEGRAM_USER.pretty_text,),
            (BotCommand.UNBAN_TELEGRAM_USER.pretty_text,),
            (BotCommand.REMOVE_TELEGRAM_USER.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)

# Подменю "Конфигурационные файлы WireGuard"
WIREGUARD_CONFIG_KEYBOARD = Keyboard(
    title="📁 Конфигурационные файлы WireGuard",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.GET_CONFIG.pretty_text,),
            (BotCommand.GET_QRCODE.pretty_text,),
            (BotCommand.SEND_CONFIG.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)

# Подменю "Статистика WireGuard"
WIREGUARD_STATS_KEYBOARD = Keyboard(
    title="📊 Статистика WireGuard",
    reply_keyboard=ReplyKeyboardMarkup(
    (        
            (BotCommand.GET_MY_STATS.pretty_text,),
            (BotCommand.GET_USER_STATS.pretty_text,),
            (BotCommand.GET_ALL_STATS.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)
    
# Подменю "Информация о пользователях Telegram"
TELEGRAM_INFO_KEYBOARD = Keyboard(
    title="👥 Информация о пользователях Telegram",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.GET_TELEGRAM_ID.pretty_text,),
            (BotCommand.GET_TELEGRAM_USERS.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)

# Подменю "Основные команды"
GENERAL_COMMANDS_KEYBOARD = Keyboard(
    title="🛠 Основные команды",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.HELP.pretty_text,),
            (BotCommand.SEND_MESSAGE.pretty_text,),
            (BotCommand.RELOAD_WG_SERVER.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)


# Подменю "Конфигурационные файлы WireGuard" для пользователей
USER_WIREGUARD_CONFIG_KEYBOARD = Keyboard(
    title="📁 Конфигурационные файлы WireGuard",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.GET_CONFIG.pretty_text,),
            (BotCommand.GET_QRCODE.pretty_text,),
            (BotCommand.REQUEST_NEW_CONFIG.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)

# Подменю "Основные команды"
USER_GENERAL_COMMANDS_KEYBOARD = Keyboard(
    title="ℹ️ Основные команды",
    reply_keyboard=ReplyKeyboardMarkup(
        (
            (BotCommand.GET_TELEGRAM_ID.pretty_text,),
            (BotCommand.GET_MY_STATS.pretty_text,),
            (BotCommand.HELP.pretty_text,),
            (keys.ButtonText.CANCEL.value.text,)
        ),
        resize_keyboard=True,
        one_time_keyboard=False,
    ),
    is_menu=True
)