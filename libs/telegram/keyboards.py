from telegram import ReplyKeyboardMarkup, KeyboardButton, KeyboardButtonRequestUsers # type: ignore
from dataclasses import dataclass


@dataclass
class KeyboardText:
    text: str


BUTTON_CLOSE = KeyboardText(text='Закрыть')
BUTTON_OWN_CONFIG = KeyboardText(text='Свои')
BUTTON_WG_USER_CONFIG = KeyboardText(text='Пользователя Wireguard')


ADMIN_MENU = ReplyKeyboardMarkup([
        ['/add_user', '/remove_user', '/com_uncom_user', '/show_users_state'],
        ['/bind_user', '/unbind_user', '/unbind_telegram_id', '/get_users_by_id', '/show_all_bindings'],
        ['/get_config', '/get_qrcode', '/send_config'],
        ['/get_telegram_id', '/get_telegram_users'],
        ['/send_message', '/help']
    ],
    one_time_keyboard=True
)

USER_MENU = ReplyKeyboardMarkup([
        ['/get_config', '/get_qrcode', '/request_new_config'],
        ['/get_telegram_id', '/help']
    ],
    one_time_keyboard=True
)

BIND_MENU = ReplyKeyboardMarkup([
        [
            KeyboardButton(
                text="Связать с пользователем",
                request_users=KeyboardButtonRequestUsers(
                    request_id=0,
                    user_is_bot=False,
                    request_username=True
                )
            ),
            BUTTON_CLOSE.text
        ]
    ],
    one_time_keyboard=True
)

CONFIG_MENU = ReplyKeyboardMarkup([
        [
            KeyboardButton(
                text="Пользователя Telegram",
                request_users=KeyboardButtonRequestUsers(
                    request_id=0,
                    user_is_bot=False,
                    request_username=True
                )
            ),
            BUTTON_WG_USER_CONFIG.text
        ],
        [
            BUTTON_OWN_CONFIG.text,
            BUTTON_CLOSE.text
        ]
    ],
    one_time_keyboard=True
)

SEND_MENU = ReplyKeyboardMarkup([
        [
            KeyboardButton(
                text="Отправить пользователю",
                request_users=KeyboardButtonRequestUsers(
                    request_id=0,
                    user_is_bot=False,
                    request_username=True
                )
            ),
            BUTTON_CLOSE.text
        ]
    ],
    one_time_keyboard=True
)
