from .commands import BotCommand
from .keyboards.keys import ButtonText

ADMIN_HELLO = (
    "👋 Добро пожаловать, администратор!\n\n"
    f"Используйте 📋 /{BotCommand.MENU} для просмотра доступных команд "
    f"или ℹ️ /{BotCommand.HELP} для справки."
)

USER_HELLO = (
    "👋 <b>Добро пожаловать!</b>\n\n"
    f"📄 Используйте /{BotCommand.REQUEST_NEW_CONFIG}, чтобы получить новый конфигурационный файл.\n\n"
    "⚠️ <b>Важно:</b> при использовании VPN запрещено раздавать торрент-трафик.\n"
    "🚫 Перед подключением к VPN убедитесь, что в вашем торрент-клиенте отключены все раздачи.\n"
    "💡 Лучше полностью закрыть торрент-клиент перед подключением.\n"
    "🔄 Оптимальный порядок действий:\n"
    "   1️⃣ Закройте торрент-клиент.\n"
    "   2️⃣ Подключитесь к VPN.\n"
    "   3️⃣ Используйте интернет с VPN.\n"
    "   4️⃣ Отключите VPN перед скачиванием торрентов.\n\n"
    f"📋 Используйте /{BotCommand.MENU} для просмотра доступных команд\n"
    f"ℹ️ Или /{BotCommand.HELP} для справки."
)


ADMIN_HELP = (
    "<b>🔹 ✨ Доступные команды: ✨ 🔹</b>\n\n"

    "<b>🔹 Основные команды: 🔹</b>\n"
    f"ℹ️ <b>/{BotCommand.HELP}</b> — показать справочную информацию\n"
    f"📋 <b>/{BotCommand.MENU}</b> — отобразить меню\n"
    f"💬 <b>/{BotCommand.SEND_MESSAGE}</b> — отправить сообщение всем пользователям\n"
    f"🚫 <b>/{BotCommand.CANCEL}</b> — отменить текущую операцию\n\n"

    "<b>🔹 Информация, связанная с Telegram: 🔹</b>\n"
    f"🆔 <b>/{BotCommand.GET_TELEGRAM_ID}</b> — узнать ваш Telegram ID\n"
    f"👥 <b>/{BotCommand.GET_TELEGRAM_USERS}</b> — получить список всех пользователей бота\n\n"

    "<b>🔹 Управление пользователями WireGuard: 🔹</b>\n"
    f"➕ <b>/{BotCommand.ADD_USER}</b> — добавить нового пользователя\n"
    f"❌ <b>/{BotCommand.REMOVE_USER}</b> — удалить пользователя\n"
    f"🔄 <b>/{BotCommand.COM_UNCOM_USER}</b> — закомментировать или раскомментировать пользователя\n"
    f"✅ <b>/{BotCommand.SHOW_USERS_STATE}</b> — показать списки активных и отключённых пользователей\n\n"

    "<b>🔹 Привязка пользователей WireGuard: 🔹</b>\n"
    f"🖇️ <b>/{BotCommand.BIND_USER}</b> — привязать пользователя WireGuard к Telegram ID\n"
    f"❎ <b>/{BotCommand.UNBIND_USER}</b> — отвязать пользователя WireGuard от Telegram ID\n"
    f"🚫 <b>/{BotCommand.UNBIND_TELEGRAM_ID}</b> — отвязать всех пользователей от данного Telegram ID\n"
    f"🔍 <b>/{BotCommand.GET_USERS_BY_ID}</b> — показать список пользователей, привязанных к Telegram ID\n"
    f"ℹ️ <b>/{BotCommand.SHOW_ALL_BINDINGS}</b> — отобразить информацию о привязанных и непривязанных пользователях\n\n"

    "<b>🔹 Управление пользователями Telegram: 🔹</b>\n"
    f"🔴 <b>/{BotCommand.BAN_TELEGRAM_USER}</b> — заблокировать пользователя телеграмм (игнорирует сообщения от пользователя и блокирует его конфиги Wireguard)\n"
    f"🟢 <b>/{BotCommand.UNBAN_TELEGRAM_USER}</b> — разблокировать пользователя телеграмм\n"
    f"🗑️ <b>/{BotCommand.REMOVE_TELEGRAM_USER}</b> — удалить пользователя телеграмм (удаляет все его конфиги Wireguard и стирает из базы данных)\n\n"

    "<b>🔹 Конфигурационные файлы WireGuard: 🔹</b>\n"
    f"📁 <b>/{BotCommand.GET_CONFIG}</b> — получить конфигурационные файлы и QR-коды\n"
    f"📷 <b>/{BotCommand.GET_QRCODE}</b> — получить QR-коды\n"
    f"📨 <b>/{BotCommand.SEND_CONFIG}</b> — отправить конфигурационные файлы и QR-коды пользователю Telegram\n\n"

    "<b>🔹 Просмотр статистики WireGuard: 🔹</b>\n"
    f"📊 <b>/{BotCommand.GET_MY_STATS}</b> — показать статистику по вашим конфигам WireGuard\n"
    f"📊 <b>/{BotCommand.GET_USER_STATS}</b> — показать статистику по конфигам WireGuard пользователя\n"
    f"📊 <b>/{BotCommand.GET_ALL_STATS}</b> — показать статистику по всем конфигурациям\n\n"
    
    "<b>🔹 Дополнительные команды: 🔹</b>\n"
    f"🔄 <b>/{BotCommand.RELOAD_WG_SERVER}</b> — перезагрузить WireGuard сервер"
)


USER_HELP = (
    "<b>🔹 ✨ Доступные команды: ✨ 🔹</b>\n\n"

    "<b>🔹 Основные команды: 🔹</b>\n"
    f"ℹ️ <b>/{BotCommand.HELP}</b> — показать справочную информацию\n"
    f"📋 <b>/{BotCommand.MENU}</b> — отобразить меню\n"
    f"🆔 <b>/{BotCommand.GET_TELEGRAM_ID}</b> — узнать ваш Telegram ID\n"
    f"📊 <b>/{BotCommand.GET_MY_STATS}</b> — показать статистику по вашим конфигам WireGuard\n\n"

    "<b>🔹 Конфигурационные файлы WireGuard: 🔹</b>\n"
    f"📁 <b>/{BotCommand.GET_CONFIG}</b> — получить все ваши конфигурационные файлы и QR-коды\n"
    f"📷 <b>/{BotCommand.GET_QRCODE}</b> — получить все ваши QR-коды\n"
    f"🙋‍♂️ <b>/{BotCommand.REQUEST_NEW_CONFIG}</b> — запросить новые конфигурационные файлы"
)

ENTER_WIREGUARD_USERNAMES_MESSAGE = (
    "Введите имена пользователей Wireguard, разделяя их пробелом.\n\n"
    f"Чтобы отменить ввод, используйте команду /{BotCommand.CANCEL}."
)

ENTER_TELEGRAM_IDS_MESSAGE = (
    "Введите Telegram Id, разделяя их пробелом.\n\n"
    f"Чтобы отменить ввод, используйте команду /{BotCommand.CANCEL}."
)

SELECT_TELEGRAM_USER = (
    f"Выберете пользователя телеграм через кнопку '{ButtonText.SELECT_TELEGRAM_USER}'.\n\n"
    f"Для выбора нескольких пользователей можете нажать '{ButtonText.ENTER_TELEGRAM_ID}'"
    " и ввести их TID через пробел.\n\n"
    f"Чтобы отменить команду, нажмите {ButtonText.CANCEL}."
)