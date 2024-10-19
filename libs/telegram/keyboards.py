from telegram import ReplyKeyboardMarkup, KeyboardButton, KeyboardButtonRequestUsers # type: ignore

ADMIN_MENU = ReplyKeyboardMarkup([
        ['/add_user', '/remove_user', '/com_uncom_user', '/show_users_state'],
        ['/bind_user', '/unbind_user', '/unbind_telegram_id', '/get_users_by_id', '/show_all_bindings'],
        ['/get_config', '/get_qrcode'],
        ['/get_telegram_id', '/get_telegram_users'],
        ['/send_message', '/help']
    ],
    one_time_keyboard=True
)

USER_MENU = ReplyKeyboardMarkup([
        ['/get_config', '/get_qrcode'],
        ['/get_telegram_id', '/help']
    ],
    one_time_keyboard=True
)

BIND_MENU = ReplyKeyboardMarkup([
        [
            KeyboardButton(
                text="Пользователи",
                request_users=KeyboardButtonRequestUsers(
                    request_id=0,
                    user_is_bot=False,
                    request_username=True
                )
            ),
            'Закрыть'
        ]
    ],
    one_time_keyboard=True
)