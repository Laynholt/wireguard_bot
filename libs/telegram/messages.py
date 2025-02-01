from .commands import BotCommands

ADMIN_HELLO = (
    "👋 Добро пожаловать, администратор!\n\n"
    f"Используйте 📋 /{BotCommands.MENU} для просмотра доступных команд "
    f"или ℹ️ /{BotCommands.HELP} для справки."
)

USER_HELLO = (
    "👋 Добро пожаловать!\n\n"
    f"Для получения нового конфигурационного файла используйте команду 📄 /{BotCommands.REQUEST_NEW_CONFIG}.\n\n"
    "⚠️ Важно: при использовании VPN нельзя раздавать торрент-трафик. Пожалуйста, отключайте все раздачи при загрузке, "
    "а после успешного скачивания полностью закрывайте торрент-клиент. В идеале, после получения файла .torrent "
    "отключайтесь от VPN, загружайте файл, выходите из торрент-клиента и только после этого снова подключайтесь к VPN.\n\n"
    f"Используйте 📋 /{BotCommands.MENU} для просмотра доступных команд "
    f"или ℹ️ /{BotCommands.HELP} для справки."
)

ADMIN_HELP = (
    "<b>🔹 ✨ Доступные команды: ✨ 🔹</b>\n\n"

    "<b>🔹 Основные команды: 🔹</b>\n"
    f"ℹ️ <b>/{BotCommands.HELP}</b> — показать справочную информацию\n"
    f"📋 <b>/{BotCommands.MENU}</b> — отобразить меню\n"
    f"💬 <b>/{BotCommands.SEND_MESSAGE}</b> — отправить сообщение всем пользователям\n"
    f"🚫 <b>/{BotCommands.CANCEL}</b> — отменить текущую операцию\n\n"

    "<b>🔹 Информация, связанная с Telegram: 🔹</b>\n"
    f"🆔 <b>/{BotCommands.GET_TELEGRAM_ID}</b> — узнать ваш Telegram ID\n"
    f"👥 <b>/{BotCommands.GET_TELEGRAM_USERS}</b> — получить список всех пользователей бота\n\n"

    "<b>🔹 Управление пользователями WireGuard: 🔹</b>\n"
    f"➕ <b>/{BotCommands.ADD_USER}</b> — добавить нового пользователя\n"
    f"❌ <b>/{BotCommands.REMOVE_USER}</b> — удалить пользователя\n"
    f"🔄 <b>/{BotCommands.COM_UNCOM_USER}</b> — закомментировать или раскомментировать пользователя\n"
    f"✅ <b>/{BotCommands.SHOW_USERS_STATE}</b> — показать списки активных и отключённых пользователей\n\n"

    "<b>🔹 Привязка пользователей WireGuard: 🔹</b>\n"
    f"🖇️ <b>/{BotCommands.BIND_USER}</b> — привязать пользователя WireGuard к Telegram ID\n"
    f"❎ <b>/{BotCommands.UNBIND_USER}</b> — отвязать пользователя WireGuard от Telegram ID\n"
    f"🚫 <b>/{BotCommands.UNBIND_TELEGRAM_ID}</b> — отвязать всех пользователей от данного Telegram ID\n"
    f"🔍 <b>/{BotCommands.GET_USERS_BY_ID}</b> — показать список пользователей, привязанных к Telegram ID\n"
    f"ℹ️ <b>/{BotCommands.SHOW_ALL_BINDINGS}</b> — отобразить информацию о привязанных и непривязанных пользователях\n\n"

    "<b>🔹 Конфигурационные файлы WireGuard: 🔹</b>\n"
    f"📁 <b>/{BotCommands.GET_CONFIG}</b> — получить конфигурационные файлы и QR-коды\n"
    f"📷 <b>/{BotCommands.GET_QRCODE}</b> — получить QR-коды\n"
    f"📨 <b>/{BotCommands.SEND_CONFIG}</b> — отправить конфигурационные файлы и QR-коды пользователю Telegram\n\n"

    "<b>🔹 Просмотр статистики WireGuard: 🔹</b>\n"
    f"📊 <b>/{BotCommands.GET_MY_STATS}</b> — показать статистику по вашим конфигам WireGuard\n"
    f"📊 <b>/{BotCommands.GET_ALL_STATS}</b> — показать статистику по всем конфигурациям\n\n"
    
    "<b>🔹 Дополнительные команды: 🔹</b>\n"
    f"🔄 <b>/{BotCommands.RELOAD_WG_SERVER}</b> — перезагрузить WireGuard сервер"
)


USER_HELP = (
    "<b>🔹 ✨ Доступные команды: ✨ 🔹</b>\n\n"

    "<b>🔹 Основные команды: 🔹</b>\n"
    f"ℹ️ <b>/{BotCommands.HELP}</b> — показать справочную информацию\n"
    f"📋 <b>/{BotCommands.MENU}</b> — отобразить меню\n"
    f"🆔 <b>/{BotCommands.GET_TELEGRAM_ID}</b> — узнать ваш Telegram ID\n"
    f"📊 <b>/{BotCommands.GET_MY_STATS}</b> — показать статистику по вашим конфигам WireGuard\n\n"

    "<b>🔹 Конфигурационные файлы WireGuard: 🔹</b>\n"
    f"📁 <b>/{BotCommands.GET_CONFIG}</b> — получить все ваши конфигурационные файлы и QR-коды\n"
    f"📷 <b>/{BotCommands.GET_QRCODE}</b> — получить все ваши QR-коды\n"
    f"🙋‍♂️ <b>/{BotCommands.REQUEST_NEW_CONFIG}</b> — запросить новые конфигурационные файлы"
)

ENTER_WIREGUARD_USERNAMES_MESSAGE = (
    "Пожалуйста, введите имена пользователей Wireguard, разделяя их пробелом.\n\n"
    f"Чтобы отменить ввод, используйте команду /{BotCommands.CANCEL}."
)