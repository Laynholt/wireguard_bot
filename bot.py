import logging
import asyncio
import threading
from typing import Optional

from telegram import SharedUser, Update, UsersShared, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    filters,
)
from telegram.error import TelegramError, NetworkError, RetryAfter, TimedOut, BadRequest

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta

from libs.wireguard import config
from libs.wireguard import stats as wireguard_stats
from libs.wireguard import user_control as wireguard
from libs.wireguard import utils as wireguard_utils

from libs.telegram.database import UserDatabase
from libs.telegram import utils as telegram_utils
from libs.telegram import wrappers, keyboards, messages
from libs.telegram.commands import BotCommands

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


database = UserDatabase(config.users_database_path)
semaphore = asyncio.Semaphore(config.telegram_max_concurrent_messages)


async def __check_database_state(update: Update) -> bool:
    """
    Проверяет, загружена ли база данных.
    Если база не загружена, оповещает пользователя и возвращает False.
    """
    if not database.db_loaded:
        logger.error("Ошибка! База данных не загружена!")
        if update.message is not None:
            await update.message.reply_text(
                "Технические неполадки. Пожалуйста, свяжитесь с администратором."
            )
        return False
    return True


async def __ensure_user_exists(telegram_id: int, update: Update) -> bool:
    """
    Проверяет состояние базы данных. Если она загружена, убеждается,
    что пользователь Telegram существует в базе. Если нет — добавляет.
    """
    if not await __check_database_state(update):
        return False

    if not database.is_telegram_user_exists(telegram_id):
        logger.info(f"Добавляю нового участника Tid [{telegram_id}].")
        database.add_telegram_user(telegram_id)
    return True


async def __end_command(update: Update, context: CallbackContext) -> None:
    """
    Универсальная функция завершения команды. Очищает данные о команде
    и предлагает меню в зависимости от прав пользователя.
    """
    if context.user_data is not None: 
        context.user_data["command"] = None
        context.user_data["wireguard_users"] = []

    if update.message is not None and update.effective_user is not None:
        await update.message.reply_text(
            f"Команда завершена. Выбрать новую команду можно из меню (/{BotCommands.MENU}).",
            reply_markup=(
                keyboards.ADMIN_MENU
                if update.effective_user.id in config.telegram_admin_ids
                else keyboards.USER_MENU
            ),
        )


# ---------------------- Команды бота ----------------------


async def start_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /start: приветствие и первичная регистрация пользователя в базе.
    """
    if update.effective_user is None:
        return
    
    telegram_id = update.effective_user.id
    if not await __ensure_user_exists(telegram_id, update):
        return

    logger.info(f"Отправляю ответ на команду [start] -> Tid [{telegram_id}].")
    if update.message is not None:
        await update.message.reply_text(
            messages.ADMIN_HELLO
            if telegram_id in config.telegram_admin_ids
            else messages.USER_HELLO
        )


async def help_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /help: показывает помощь по доступным командам.
    """
    if update.effective_user is None:
        return
    
    telegram_id = update.effective_user.id
    if not await __ensure_user_exists(telegram_id, update):
        return

    logger.info(f"Отправляю ответ на команду [help] -> Tid [{telegram_id}].")
    if update.message is not None:
        await update.message.reply_text(
            messages.ADMIN_HELP
            if telegram_id in config.telegram_admin_ids
            else messages.USER_HELP,
            parse_mode="HTML",
        )
    await __end_command(update, context)


async def menu_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /menu: выводит меню в зависимости от прав пользователя.
    """
    if update.effective_user is None:
        return
    
    telegram_id = update.effective_user.id
    if not await __ensure_user_exists(telegram_id, update):
        return

    logger.info(f"Отправляю ответ на команду [menu] -> Tid [{telegram_id}].")
    if update.message is not None:
        await update.message.reply_text(
            "📌 <b>Выберите команду из меню.</b>",
            reply_markup=(
                keyboards.ADMIN_MENU
                if telegram_id in config.telegram_admin_ids
                else keyboards.USER_MENU
            ),
            parse_mode="HTML"
        )


async def get_telegram_id_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_telegram_id: выводит телеграм-ID пользователя.
    """
    if update.effective_user is None:
        return
    
    telegram_id = update.effective_user.id
    if not await __ensure_user_exists(telegram_id, update):
        return

    logger.info(f"Отправляю ответ на команду [get_telegram_id] -> Tid [{telegram_id}].")
    if update.message is not None:
        await update.message.reply_text(f"🆔 Ваш идентификатор: {telegram_id}.")
    await __end_command(update, context)


async def request_new_config_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /request_new_config: пользователь запрашивает у админов новый конфиг.
    """
    if update.effective_user is None:
        return
    
    if update.message is not None:
        await update.message.reply_text(
            "📥 <b>Запрос на конфигурацию WireGuard отправлен.</b>\n\n"
            "🔄 Ожидайте, пока администратор обработает ваш запрос.\n"
            "📂 Как только файл будет готов, он будет отправлен вам в этом чате.",
            parse_mode="HTML"
        )
    
    telegram_id = update.effective_user.id
    telegram_name = await telegram_utils.get_username_by_id(telegram_id, context)

    for admin_id in config.telegram_admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"Пользователь [{telegram_name} ({telegram_id})] "
                    f"запросил новый конфиг Wireguard."
                ),
            )
            logger.info(
                f"Сообщение о запросе нового конфига от [{telegram_name} ({telegram_id})] "
                f"отправлено админу {admin_id}."
            )
        except TelegramError as e:
            logger.error(f"Не удалось отправить сообщение админу {admin_id}: {e}.")

    await __end_command(update, context)


@wrappers.admin_required
async def get_telegram_users_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_telegram_users: выводит всех телеграм-пользователей, которые
    взаимодействовали с ботом (есть в БД).
    """
    if update.effective_user is None:
        return
    
    telegram_id = update.effective_user.id
    if not database.db_loaded:
        logger.error("Ошибка! База данных не загружена!")
        if update.message is not None:
            await update.message.reply_text("Не удалось получить данные из базы данных.")
        return

    telegram_ids = database.get_all_telegram_users()
    logger.info(f"Отправляю список телеграм-пользователей -> Tid [{telegram_id}].")

    if not telegram_ids:
        if update.message is not None:
            await update.message.reply_text("У бота пока нет активных Telegram пользователей.")
        await __end_command(update, context)
        return

    telegram_usernames = await telegram_utils.get_usernames_in_bulk(
        telegram_ids, context, semaphore
    )

    header = f"<b>📋 Telegram Id всех пользователей бота [{len(telegram_ids)}]</b>\n\n"
    user_lines = [
        f"{index}. {telegram_usernames.get(tid, 'Нет имени пользователя')} ({tid})\n"
        for index, tid in enumerate(telegram_ids, start=1)
    ]

    if update.message is not None:
        await update.message.reply_text(header + "".join(user_lines), parse_mode="HTML")

    await __end_command(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def add_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /add_user: добавляет нового пользователя Wireguard.
    """
    if update.message is not None:
        await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
    if context.user_data is not None: 
        context.user_data["command"] = BotCommands.ADD_USER
        context.user_data["wireguard_users"] = []


@wrappers.admin_required
@wrappers.command_lock
async def remove_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /remove_user: удаляет существующего пользователя Wireguard.
    """
    if update.message is not None:
        await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
    if context.user_data is not None:
        context.user_data["command"] = BotCommands.REMOVE_USER


@wrappers.admin_required
@wrappers.command_lock
async def com_uncom_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /com_uncom_user: комментирует/раскомментирует (блокирует/разблокирует)
    пользователей Wireguard (путём комментирования в конфиге).
    """
    if update.message is not None:
        await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
    if context.user_data is not None:
        context.user_data["command"] = BotCommands.COM_UNCOM_USER


@wrappers.admin_required
@wrappers.command_lock
async def bind_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /bind_user: привязывает существующие конфиги Wireguard к Telegram-пользователю.
    """
    if update.message is not None:
        await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
    if context.user_data is not None:
        context.user_data["command"] = BotCommands.BIND_USER
        context.user_data["wireguard_users"] = []


@wrappers.admin_required
@wrappers.command_lock
async def unbind_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /unbind_user: отвязывает конфиги Wireguard от Telegram-пользователя (по user_name).
    """
    if update.message is not None:
        await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
    if context.user_data is not None:
        context.user_data["command"] = BotCommands.UNBIND_USER


@wrappers.admin_required
@wrappers.command_lock
async def send_message_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /send_message: рассылает произвольное сообщение всем зарегистрированным в БД.
    """
    if update.message is not None:
        await update.message.reply_text(
            (
                "Введите текст для рассылки.\n\n"
                f"Чтобы отменить ввод, используйте команду /{BotCommands.CANCEL}."
            )
        )
    if context.user_data is not None:
        context.user_data["command"] = BotCommands.SEND_MESSAGE


@wrappers.admin_required
async def cancel_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /cancel: универсальная отмена действия для администратора.
    """
    if update.message is not None:
        await update.message.reply_text(
            f"Действие отменено. Можете начать сначала, выбрав команду из меню (/{BotCommands.MENU}).",
            reply_markup=keyboards.ADMIN_MENU,
        )
    if context.user_data is not None:
        context.user_data["command"] = None


@wrappers.admin_required
@wrappers.command_lock
async def unbind_telegram_id_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /unbind_telegram_id: отвязывает все конфиги Wireguard по конкретному Telegram ID.
    """
    if update.message is not None:
        await update.message.reply_text(
            (
                "Пожалуйста, выберите пользователя Telegram, которого хотите отвязать.\n\n"
                "Для отмены действия нажмите кнопку Закрыть."
            ),
            reply_markup=keyboards.UNBIND_MENU,
        )
    if context.user_data is not None:
        context.user_data["command"] = BotCommands.UNBIND_TELEGRAM_ID


@wrappers.admin_required
@wrappers.command_lock
async def get_bound_users_by_telegram_id_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_users_by_id: показать, какие конфиги Wireguard привязаны к Telegram ID.
    """
    if update.message is not None:
        await update.message.reply_text(
            (
                "Пожалуйста, выберите пользователя Telegram, привязки которого хотите увидеть.\n\n"
                "Для отмены действия нажмите кнопку Закрыть."
            ),
            reply_markup=keyboards.BINDINGS_MENU,
        )
    if context.user_data is not None:
        context.user_data["command"] = BotCommands.GET_USERS_BY_ID


@wrappers.admin_required
@wrappers.command_lock
async def send_config_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /send_config: администратор отправляет конкретные конфиги Wireguard выбранным пользователям.
    """
    if update.message is not None:
        await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
    if context.user_data is not None:
        context.user_data["command"] = BotCommands.SEND_CONFIG
        context.user_data["wireguard_users"] = []


@wrappers.admin_required
async def show_users_state_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /show_users_state: отображает состояние пользователей (активные/отключённые).
    """
    if update.effective_user is None:
        return
    
    telegram_id = update.effective_user.id

    if not database.db_loaded:
        logger.error("Ошибка! База данных не загружена!")
        if update.message is not None:
            await update.message.reply_text("Не удалось получить данные из базы данных.")
        return

    linked_users = database.get_all_linked_data()
    active_usernames = sorted(wireguard.get_active_usernames())
    inactive_usernames = sorted(wireguard.get_inactive_usernames())

    linked_dict = {}
    for tid, user_name in linked_users:
        linked_dict[user_name] = tid

    active_telegram_ids = [
        linked_dict.get(user_name, "Нет привязки") for user_name in active_usernames
    ]
    inactive_telegram_ids = [
        linked_dict.get(user_name, "Нет привязки") for user_name in inactive_usernames
    ]

    active_telegram_names_dict = await telegram_utils.get_usernames_in_bulk(
        [
            tid
            for tid in active_telegram_ids
            if telegram_utils.validate_telegram_id(tid)
        ],
        context,
        semaphore,
    )
    inactive_telegram_names_dict = await telegram_utils.get_usernames_in_bulk(
        [
            tid
            for tid in inactive_telegram_ids
            if telegram_utils.validate_telegram_id(tid)
        ],
        context,
        semaphore,
    )

    message_parts = []
    message_parts.append(f"<b>🔹 Активные пользователи [{len(active_usernames)}] 🔹</b>\n")
    for index, user_name in enumerate(active_usernames, start=1):
        tid = linked_dict.get(user_name, "Нет привязки")
        telegram_username = active_telegram_names_dict.get(tid, "Нет имени пользователя")
        message_parts.append(f"{index}. <code>{user_name}</code> - {telegram_username} ({tid})\n")

    message_parts.append(
        f"\n<b>🔹 Отключенные пользователи [{len(inactive_usernames)}] 🔹</b>\n"
    )
    for index, user_name in enumerate(inactive_usernames, start=1):
        tid = linked_dict.get(user_name, "Нет привязки")
        telegram_username = inactive_telegram_names_dict.get(
            tid, "Нет имени пользователя"
        )
        message_parts.append(f"{index}. <code>{user_name}</code> - {telegram_username} ({tid})\n")

    logger.info(
        f"Отправляю информацию об активных и отключенных пользователях -> Tid [{telegram_id}]."
    )
    await telegram_utils.send_long_message(
        update, "".join(message_parts), parse_mode="HTML"
    )
    await __end_command(update, context)


@wrappers.admin_required
async def show_all_bindings_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /show_all_bindings: показывает все привязки:
    - Какие пользователи Wireguard привязаны к каким Telegram ID,
    - Список непривязанных Telegram ID,
    - Список непривязанных user_name.
    """
    if update.effective_user is None:
        return
    
    telegram_id = update.effective_user.id

    if not database.db_loaded:
        logger.error("Ошибка! База данных не загружена!")
        if update.message is not None:
            await update.message.reply_text("Не удалось получить данные из базы данных.")
        return

    linked_users = database.get_all_linked_data()
    telegram_ids_in_users = database.get_all_telegram_users()
    available_usernames = wireguard.get_usernames()

    # Словарь вида {telegram_id: [user_names]}
    linked_dict = {}
    for tid, user_name in linked_users:
        linked_dict.setdefault(tid, []).append(user_name)

    # Определяем всех Telegram-пользователей, у которых есть привязки
    linked_telegram_ids = list(linked_dict.keys())
    linked_telegram_names_dict = await telegram_utils.get_usernames_in_bulk(
        linked_telegram_ids, context, semaphore
    )

    message_parts = [f"<b>🔹🔐 Привязанные пользователи [{len(linked_dict)}] 🔹</b>\n"]
    for index, (tid, user_names) in enumerate(linked_dict.items(), start=1):
        user_names_str = ", ".join([f"<code>{u}</code>" for u in sorted(user_names)])
        telegram_username = linked_telegram_names_dict.get(tid, "Нет имени пользователя")
        message_parts.append(f"{index}. {telegram_username} ({tid}): {user_names_str}\n")

    # Непривязанные Telegram ID
    unlinked_telegram_ids = set(telegram_ids_in_users) - set(linked_telegram_ids)
    if unlinked_telegram_ids:
        unlinked_telegram_names_dict = await telegram_utils.get_usernames_in_bulk(
            list(unlinked_telegram_ids), context, semaphore
        )
        message_parts.append(
            f"\n<b>🔹❌ Непривязанные Telegram Id [{len(unlinked_telegram_ids)}] 🔹</b>\n"
        )
        for index, tid in enumerate(unlinked_telegram_ids, start=1):
            telegram_username = unlinked_telegram_names_dict.get(
                tid, "Нет имени пользователя"
            )
            message_parts.append(f"{index}. {telegram_username} ({tid})\n")

    # Непривязанные user_name
    linked_usernames = {u for _, u in linked_users}
    unlinked_usernames = set(available_usernames) - linked_usernames
    if unlinked_usernames:
        message_parts.append(
            f"\n<b>🔹🛡️ Непривязанные конфиги Wireguard [{len(unlinked_usernames)}] 🔹</b>\n"
        )
        for index, user_name in enumerate(sorted(unlinked_usernames), start=1):
            message_parts.append(f"{index}. <code>{user_name}</code>\n")

    logger.info(
        f"Отправляю информацию о привязанных и непривязанных пользователях -> Tid [{telegram_id}]."
    )
    await telegram_utils.send_long_message(
        update, "".join(message_parts), parse_mode="HTML"
    )
    await __end_command(update, context)


async def __get_configuration(
    update: Update, command: BotCommands, telegram_id: int
) -> None:
    """
    Универсальная функция получения и отправки пользователю конфигурационных файлов/QR-кода.
    """
    if update.effective_user is None:
        return
    
    if update.message is None:
        return
    
    requester_telegram_id = update.effective_user.id

    if not database.db_loaded:
        logger.error("Ошибка! База данных не загружена!")
        await update.message.reply_text(
            "Не удалось получить данные из базы данных. "
            "Пожалуйста, свяжитесь с администратором."
        )
        return

    # Если пользователь сам запрашивает конфиг, проверить, есть ли он в базе
    if requester_telegram_id == telegram_id:
        if not database.is_telegram_user_exists(telegram_id):
            logger.info(f"Добавляю пользователя Tid [{telegram_id}] в базу данных.")
            database.add_telegram_user(telegram_id)

    user_names = database.get_users_by_telegram_id(telegram_id)
    if not user_names:
        logger.info(f"Пользователь Tid [{telegram_id}] не привязан ни к одной конфигурации.")
        await update.message.reply_text(
            "Ваши конфигурации не найдены. "
            "Пожалуйста, свяжитесь с администратором для добавления новых."
        )
        return

    for user_name in user_names:
        await __get_user_configuration(update, command, user_name)


async def __get_user_configuration(
    update: Update, command: BotCommands, user_name: str
) -> None:
    """
    Отправляет пользователю .zip-конфиг или QR-код в зависимости от команды.
    Если пользователь заблокирован или конфиг отсутствует, выводится соответствующее сообщение.
    """
    if update.effective_user is None:
        return
    
    if update.message is None:
        return
    
    requester_telegram_id = update.effective_user.id

    # Форматируем имя конфига для сообщений
    formatted_user = f"🔐 <em>{user_name}</em>"

    # Проверка существования конфига
    user_exists_result = wireguard.check_user_exists(user_name)
    if not user_exists_result.status:
        logger.error(f"Конфиг [{user_name}] не найден. Удаляю привязку.")
        await update.message.reply_text(
            f"🚫 Конфигурация {formatted_user} была удалена\n\n"
            f"<em>Пожалуйста, свяжитесь с администратором для создания новой</em>",
            parse_mode="HTML"
        )
        database.delete_user(user_name)
        return

    if wireguard.is_username_commented(user_name):
        logger.info(f"Конфиг [{user_name}] на данный момент закомментирован.")
        await update.message.reply_text(
            f"⚠️ Конфигурация {formatted_user} временно заблокирована\n\n"
            f"<em>Причина: администратор ограничил доступ</em>",
            parse_mode="HTML"
        )
        return

    if command == BotCommands.GET_CONFIG:
        logger.info(
            f"Создаю и отправляю Zip-архив пользователя Wireguard [{user_name}] "
            f"пользователю Tid [{requester_telegram_id}]."
        )
        
        zip_result = wireguard.create_zipfile(user_name)
        if zip_result.status:
            # Экранируем все специальные символы
            caption = (
                f"<b>📦 Архив конфигурации</b>\n"
                f"╔━━━━━━━━━━━━━━━━━━\n"
                f"│ <i>Содержимое:</i>\n"
                f"│▸ 📄 Файл конфигурации\n"
                f"│▸ 📲 QR-код для быстрого подключения\n"
                f"╚━━━━━━━━━━━━━━━━━━\n\n"
                f"🔧 <b>Конфигурация:</b> {formatted_user}\n\n"
                f"╔━━━━━━━━━━━━━━━━━━\n"
                f"│▸ 📂 Распакуйте архив\n"
                f"│▸ 🛡 Откройте приложение WireGuard\n"
                f"│▸ ➕ Нажмите «добавить туннель» (+)\n"
                f"│▸ 📷 Отсканируйте QR-код\n"
                f"│▸ ⚙️ Или импортируйте .conf файл\n"
                f"╚━━━━━━━━━━━━━━━━━━"
            )
            
            await update.message.reply_document(
                document=open(zip_result.description, "rb"),
                caption=caption,
                parse_mode="HTML"
            )
            wireguard.remove_zipfile(user_name)
        else:
            logger.error(f'Не удалось создать архив для {user_name}. Ошибка: [{zip_result.description}]')
            await update.message.reply_text(
                f"❌ Не удалось создать архив для {formatted_user}\n"
                f"<em>Ошибка: {zip_result.description}</em>",
                parse_mode="HTML"
            )

    elif command == BotCommands.GET_QRCODE:
        logger.info(
            f"Создаю и отправляю Qr-код пользователя Wireguard [{user_name}] "
            f"пользователю Tid [{requester_telegram_id}]."
        )
        
        png_path = wireguard.get_qrcode_path(user_name)
        if png_path.status:
            caption = (
                "<b>📲 QR-код для подключения</b>\u2003\u2003\u2003\n"
                "━━━━━━━━━━━━━━━━\n\n"
                f"🔧 <b>Конфигурация:</b> {formatted_user}\n\n"
                "╔━━━━━━━━━━━━━━━\n"
                "│▸ 🛡 Откройте приложение WireGuard\n"
                "│▸ ➕ Нажмите «добавить туннель» (+)\n"
                "│▸ 📷 Отсканируйте QR-код\n"
                "╚━━━━━━━━━━━━━━━"
            )
            
            await update.message.reply_photo(
                photo=open(png_path.description, "rb"),
                caption=caption,
                parse_mode="HTML"
            )
        else:
            logger.error(f'Не удалось создать архив для {user_name}. Ошибка: [{png_path.description}]')
            await update.message.reply_text(
                f"❌ Не удалось сгенерировать QR-код для {formatted_user}\n"
                f"<em>Ошибка: {png_path.description}</em>",
                parse_mode="HTML"
            )


@wrappers.command_lock
async def get_config_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_config: выдаёт пользователю .zip конфигурации Wireguard.
    Если пользователь администратор — позволяет выбрать, чьи конфиги получать.
    """
    await __get_config_or_qrcode_helper(
        update=update,
        context=context,
        command=BotCommands.GET_CONFIG,
        message=(
            "Выберете, чьи файлы конфигурации вы хотите получить.\n\n"
            "Для отмены действия нажмите кнопку Закрыть."
        )
    )


@wrappers.command_lock
async def get_qrcode_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_qrcode: выдаёт пользователю QR-код конфигурации Wireguard.
    Если пользователь администратор — позволяет выбрать, чьи QR-коды получать.
    """
    await __get_config_or_qrcode_helper(
        update=update,
        context=context,
        command=BotCommands.GET_QRCODE,
        message=(
            "Выберете, чьи Qr-код файлы конфигурации вы хотите получить.\n\n"
            "Для отмены действия нажмите кнопку Закрыть."
        )
    )


async def __get_config_or_qrcode_helper(
    update: Update,
    context: CallbackContext,
    command: BotCommands,
    message: str
) -> None:
    if update.effective_user is None:
        return

    if update.message is None:
        return
    
    telegram_id = update.effective_user.id
    if telegram_id in config.telegram_admin_ids:
        if context.user_data is not None:
            context.user_data["command"] = command
        await update.message.reply_text(message,reply_markup=keyboards.CONFIG_MENU)
    else:
        await __get_configuration(update, command=command, telegram_id=telegram_id)
        await __end_command(update, context)
        

async def get_my_stats_command(update: Update, context: CallbackContext) -> None:
    """
    Команда для пользователей (доступна всем).
    Выводит статистику по конфигам WireGuard, привязанным к текущему Telegram ID.
    Если конфиг недоступен или отсутствует (удалён), информация об этом
    выводится в сообщении. При необходимости лишние записи удаляются из БД.
    """
    if update.effective_user is None:
        return
    
    if update.message is None:
        return
    
    telegram_id = update.effective_user.id

    if not await __check_database_state(update):
        return

    wireguard_users = database.get_users_by_telegram_id(telegram_id)
    if not wireguard_users:
        await update.message.reply_text(
            "У вас ещё нет конфигурационных файлов Wireguard.\n\n"
            f"Используйте /{BotCommands.REQUEST_NEW_CONFIG} для запроса их у администратора."
        )
        await __end_command(update, context)
        return

    # Получаем полную статистику
    all_wireguard_stats = wireguard_stats.accumulate_wireguard_stats(
        conf_file_path=config.wireguard_config_filepath,
        json_file_path=config.wireguard_log_filepath,
        sort_by=wireguard_stats.SortBy.TRANSFER_SENT,
    )

    lines = []
    inactive_usernames = wireguard.get_inactive_usernames()
    
    for i, wg_user in enumerate(wireguard_users, start=1):
        user_data = all_wireguard_stats.get(wg_user, None)

        # Случай, когда статистики для пользователя нет
        if user_data is None:
            # Проверяем, существует ли конфиг этого пользователя фактически
            check_result = wireguard.check_user_exists(wg_user)
            if check_result.status:
                remove_result = wireguard.remove_user(wg_user)
                if remove_result.status:
                    logger.info(remove_result.description)
                else:
                    logger.error(remove_result.description)

            # Если пользователь есть в БД, но конфиг отсутствует — удаляем из БД
            if database.delete_user(wg_user):
                logger.info(f"Пользователь [{wg_user}] удалён из базы данных.")
            else:
                logger.error(
                    f"Не удалось удалить информацию о пользователе [{wg_user}] из базы данных."
                )

            continue

        # Если всё в порядке, формируем строку со статистикой
        lines.append(
            f"\n<b>{i}]</b>] <b>🌐 Конфиг:</b> <i>{wg_user}</i> "
            f"{'🔴 <b>[Неактивен]</b>' if wg_user in inactive_usernames else '🟢 <b>[Активен]</b>'}\n"
            f"   📡 IP: {user_data.allowed_ips}\n"
            f"   📤 Отправлено: {user_data.transfer_received if user_data.transfer_received else 'N/A'}\n"
            f"   📥 Получено: {user_data.transfer_sent if user_data.transfer_sent else 'N/A'}\n"
            f"   ━━━━━━━━━━━━━━━━"
        )

    logger.info(f"Отправляю статистику по личным конфигам Wireguard -> Tid [{telegram_id}].")
    
    # Разбиваем на батчи по указанному размеру
    batch_size = 5
    batched_lines = [
        lines[i:i + batch_size]
        for i in range(0, len(lines), batch_size)
    ]
    
    await telegram_utils.send_batched_messages(
        update=update,
        batched_lines=batched_lines,
        parse_mode=None,
        groups_before_delay=2,
        delay_between_groups=0.5
    )

    await __end_command(update, context)


@wrappers.admin_required
async def get_all_stats_command(update: Update, context: CallbackContext) -> None:
    """
    Команда для администраторов.
    Выводит статистику для всех конфигов WireGuard, включая информацию о владельце
    (Telegram ID и username). Если владелец не привязан, выводит соответствующую пометку.
    """
    if update.message is None:
        return
    
    # Сначала получаем всю статистику
    all_wireguard_stats = wireguard_stats.accumulate_wireguard_stats(
        conf_file_path=config.wireguard_config_filepath,
        json_file_path=config.wireguard_log_filepath,
        sort_by=wireguard_stats.SortBy.TRANSFER_SENT,
    )

    if not all_wireguard_stats:
        await update.message.reply_text("Нет данных по ни одному конфигу.")
        await __end_command(update, context)
        return

    if not await __check_database_state(update):
        return

    # Получаем все связки (владелец <-> конфиг)
    linked_users = database.get_all_linked_data()
    linked_dict = {user_name: tid for tid, user_name in linked_users}

    # Достаем username для всех владельцев (bulk-запрос)
    linked_telegram_ids = set(linked_dict.values())
    linked_telegram_names_dict = await telegram_utils.get_usernames_in_bulk(
        linked_telegram_ids, context, semaphore
    )

    lines = []
    inactive_usernames = wireguard.get_inactive_usernames()
    
    for i, (wg_user, user_data) in enumerate(all_wireguard_stats.items(), start=1):
        owner_tid = linked_dict.get(wg_user)
        if owner_tid is not None:
            owner_username = linked_telegram_names_dict.get(owner_tid, "Нет имени пользователя")
            owner_part = f" 👤 Владелец: {owner_username} (ID: {owner_tid})"
        else:
            owner_part = " 👤 Владелец: не назначен"

        status_icon = "🔴 [НЕАКТИВЕН]" if wg_user in inactive_usernames else "🟢 [АКТИВЕН]"

        lines.append(
            f"\n{i}] 🌐 Конфиг: {wg_user} {status_icon}\n"
            f"   {owner_part}\n"
            f"   📡 IP: {user_data.allowed_ips}\n"
            f"   📤 Отправлено: {(user_data.transfer_sent if user_data.transfer_sent else 'N/A').ljust(10)}"
            f"   📥 Получено: {user_data.transfer_received if user_data.transfer_received else 'N/A'}\n"
            f"   ────────────────"
        )

    tid = -1
    if update.effective_user is not None:
        tid = update.effective_user.id
    
    logger.info(f"Отправляю статистику по всем конфигам Wireguard -> Tid [{tid}].")
    
    # Разбиваем на батчи по указанному размеру
    batch_size = 5
    batched_lines = [
        lines[i:i + batch_size]
        for i in range(0, len(lines), batch_size)
    ]
    
    await telegram_utils.send_batched_messages(
        update=update,
        batched_lines=batched_lines,
        parse_mode=None,
        groups_before_delay=2,
        delay_between_groups=0.5
    )

    await __end_command(update, context)


@wrappers.admin_required
async def reload_wireguard_server_command(update: Update, context: CallbackContext) -> None:
    """
    Обработчик команды перезагрузки сервера Wireguard.
    """
    if update.message is not None:
        await update.message.reply_text("🔄 Перезагружаю сервер WireGuard...")
    
    try:
        # await asyncio.to_thread(wireguard_utils.log_and_restart_wireguard)
        success = await __async_restart_wireguard()
        response = (
            "✅ Сервер WireGuard успешно перезагружен!"
            if success
            else "❌ Ошибка! Не удалось перезагрузить Wireguard!"
        )
    except Exception as e:
        response = f"⚠️ Ошибка: {str(e)}"
        
    if update.message is not None:
        await update.message.reply_text(response)

    await __end_command(update, context)


async def __async_restart_wireguard() -> bool:
    """Асинхронная обертка для синхронной операции перезагрузки WireGuard.
    
    Запускает блокирующую операцию в отдельном потоке, чтобы не блокировать event loop.
    
    Returns:
        bool: Результат операции перезагрузки
            - True: перезагрузка успешно выполнена
            - False: произошла ошибка при перезагрузке
            
    Raises:
        Exception: Любые исключения из wireguard_utils.log_and_restart_wireguard 
            будут перехвачены и залогированы, но не проброшены выше
            
    Notes:
        - Использует дефолтный ThreadPoolExecutor
        - Является internal-функцией (не предназначена для прямого вызова)
    """
    loop = asyncio.get_running_loop()   
    try:
        return await loop.run_in_executor(
            None,
            wireguard_utils.log_and_restart_wireguard
        )
    except Exception as e:
        logger.error(f"Ошибка перезагрузки: {str(e)}")
        return False


async def reload_wireguard_server_schedule():
    """Периодическая задача для автоматической перезагрузки WireGuard.
    
    Features:
        - Запускается по расписанию через APScheduler
        - Полностью асинхронная реализация
        - Интеграция с системой логирования
        
    Behavior:
        1. Инициирует перезагрузку через __async_restart_wireguard()
        2. Логирует результат операции
        3. Перехватывает и логирует любые исключения
        
    Schedule:
        - Первый запуск: через 10 секунд после старта приложения
        - Интервал: каждые 7 дней
        
    Notes:
        - Не принимает параметров и не возвращает значений
        - Для работы требует предварительной настройки планировщика
    """
    logger.info("Запуск автоматической перезагрузки Wireguard...")
    try:
        success = await __async_restart_wireguard()
        logger.info(f"Перезагрузка прошла: {'успешно' if success else 'неудачно'}!")
    except Exception as e:
        logger.error(f"Ошибка в расписании: {str(e)}")


def setup_scheduler():
    """Инициализация и настройка планировщика задач.
    
    Actions:
        1. Создает новую job-задачу
        2. Настраивает триггер типа IntervalTrigger
        3. Запускает scheduler
        
    Job Parameters:
        - Функция: reload_wireguard_server_schedule
        - Триггер: интервальный (7 дней)
        - Первый запуск: через 10 секунд после старта
        
    Architecture:
        - Использует AsyncIOScheduler для интеграции с asyncio
        - Планировщик работает в том же event loop, что и Telegram бот
        
    Notes:
        - Должна быть вызвана один раз при старте приложения
        - Для остановки используйте scheduler.shutdown()
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    scheduler = AsyncIOScheduler(event_loop=loop)  # Передаём loop явно
    scheduler.add_job(
        reload_wireguard_server_schedule,
        trigger=IntervalTrigger(days=7),
        next_run_time=datetime.now() + timedelta(seconds=10)
    )
    scheduler.start()
    logger.info("Планировщик запущен.")
    loop.run_forever()  # Держим event loop активным


async def unknown_command(update: Update, context: CallbackContext) -> None:
    """
    Обработчик неизвестных команд.
    """
    if update.message is not None:
        await update.message.reply_text(
            f"Неизвестная команда. Используйте /{BotCommands.HELP} для просмотра доступных команд."
        )


# ---------------------- Обработка входящих сообщений ----------------------


async def handle_text(update: Update, context: CallbackContext) -> None:
    """
    Обработчик текстовых сообщений, в которых пользователи вводят имена
    пользователей Wireguard или другие данные после команды.
    """
    clear_command_flag = True
    try:
        if context.user_data is None:
            return
        
        if update.message is None:
            return
        
        current_command = context.user_data.get("command", None)

        # Если нет команды, предлагаем меню
        if current_command is None:
            if update.effective_user is not None:
                await update.message.reply_text(
                    f"Пожалуйста, выберите команду из меню. (/{BotCommands.MENU})",
                    reply_markup=(
                        keyboards.ADMIN_MENU
                        if update.effective_user.id in config.telegram_admin_ids
                        else keyboards.USER_MENU
                    ),
                )
            clear_command_flag = False
            return

        # Нажата кнопка «Закрыть»?
        if update.message.text == keyboards.BUTTON_CLOSE.text:
            if await __close_button_handler(update, context):
                return

        # Обработка нажатия кнопки Own Config / Wg User Config
        if (
            current_command in (BotCommands.GET_CONFIG, BotCommands.GET_QRCODE)
            and update.message.text in (
                keyboards.BUTTON_OWN.text,
                keyboards.BUTTON_WG_USER_CONFIG.text
            )
        ):
            if await __get_config_buttons_handler(update, context):
                clear_command_flag = False
                return
            
        # Обработка нажатия кнопки Bind to YourSelf
        if (
            current_command == BotCommands.BIND_USER
            and update.message.text == keyboards.BUTTON_BIND_TO_YOURSELF.text
        ):
            if update.effective_user is not None:
                await __delete_message(update, context)
                await __bind_users(update, context, update.effective_user.id)
            return
        
        # Обработка нажатия кнопки Unbind from YourSelf
        if (
            current_command == BotCommands.UNBIND_TELEGRAM_ID
            and update.message.text == keyboards.BUTTON_UNBIND_FROM_YOURSELF.text
        ):
            if update.effective_user is not None:
                await __delete_message(update, context)
                await __unbind_telegram_id(update, context, update.effective_user.id)
            return
        
        # Обработка нажатия кнопки Own
        if (
            current_command == BotCommands.GET_USERS_BY_ID
            and update.message.text == keyboards.BUTTON_OWN.text
        ):
            if update.effective_user is not None:
                await __delete_message(update, context)
                await __get_bound_users_by_tid(update, context, update.effective_user.id)
            return

        # Обработка /cancel
        if update.message.text is not None and update.message.text.lower() == f'/{BotCommands.CANCEL}':
            await cancel_command(update, context)
            clear_command_flag = False
            return

        # Если это рассылка
        if current_command == BotCommands.SEND_MESSAGE:
            await __send_message_to_all(update, context)
            return

        need_restart_wireguard = False
        if update.message.text is not None:
            entries = update.message.text.split()
        else:
            entries = []

        for entry in entries:
            ret_val = None

            if current_command == BotCommands.ADD_USER:
                ret_val = await __add_user(update, context, entry)

            elif current_command == BotCommands.REMOVE_USER:
                ret_val = await __rem_user(update, entry)

            elif current_command == BotCommands.COM_UNCOM_USER:
                ret_val = await __com_user(update, entry)

            elif current_command in (BotCommands.BIND_USER, BotCommands.SEND_CONFIG):
                ret_val = await __create_list_of_wireguard_users(update, context, entry)

            elif current_command == BotCommands.UNBIND_USER:
                await __unbind_user(update, entry)

            elif current_command in (BotCommands.GET_CONFIG, BotCommands.GET_QRCODE):
                await __get_user_configuration(update, current_command, entry)

            if ret_val is not None:
                # Выводим сообщение с результатом (ошибка или успех)
                await update.message.reply_text(ret_val.description)
                if ret_val.status:
                    logger.info(ret_val.description)
                    need_restart_wireguard = True
                else:
                    logger.error(ret_val.description)

        # Если требуется перезапуск WireGuard после изменений
        if need_restart_wireguard:
            restart_thread = threading.Thread(
                target=wireguard_utils.log_and_restart_wireguard, daemon=True
            )
            restart_thread.start()
            need_restart_wireguard = False

        # Для add_user / bind_user предлагаем выбрать пользователя Telegram
        if current_command in (BotCommands.ADD_USER, BotCommands.BIND_USER):
            if len(context.user_data["wireguard_users"]) > 0 and update.message:
                await update.message.reply_text(
                    (
                        "Нажмите на кнопку выбора пользователя, чтобы выбрать пользователя Telegram "
                        "для связывания с переданными конфигами Wireguard.\n\n"
                        "Для отмены связывания, нажмите кнопку Закрыть."
                    ),
                    reply_markup=keyboards.BIND_MENU,
                )
                clear_command_flag = False

        # Для /send_config — аналогичная логика
        elif current_command == BotCommands.SEND_CONFIG:
            if len(context.user_data["wireguard_users"]) > 0 and update.message:
                await update.message.reply_text(
                    (
                        "Нажмите на кнопку выбора пользователя, чтобы выбрать пользователя Telegram,"
                        " которому отправить выбранные конфиги Wireguard.\n\n"
                        "Для отмены нажмите кнопку Закрыть."
                    ),
                    reply_markup=keyboards.SEND_MENU,
                )
                clear_command_flag = False

    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        if update.message is not None:
            await update.message.reply_text(
                "Произошла неожиданная ошибка. Пожалуйста, попробуйте еще раз позже."
            )
    finally:
        if clear_command_flag:
            await __end_command(update, context)


async def handle_user_request(update: Update, context: CallbackContext) -> None:
    """
    Обработчик, который срабатывает, когда пользователь шлёт запрос
    с кнопкой выбора Telegram-пользователя (filters.StatusUpdate.USER_SHARED).
    """
    clear_command_flag = True
    try:
        await __delete_message(update, context)

        if context.user_data is None:
            return
        
        if update.message is None:
            return

        current_command = context.user_data.get("command", None)
        if current_command is None:
            if update.effective_user is not None:
                await update.message.reply_text(
                    f"Пожалуйста, выберите команду из меню. (/{BotCommands.MENU})",
                    reply_markup=(
                        keyboards.ADMIN_MENU
                        if update.effective_user.id in config.telegram_admin_ids
                        else keyboards.USER_MENU
                    ),
                )
            clear_command_flag = False
            return

        if update.message.users_shared is None:
            return

        for shared_user in update.message.users_shared.users:
            if current_command in (BotCommands.ADD_USER, BotCommands.BIND_USER):
                await __bind_users(update, context, shared_user.user_id)

            elif current_command == BotCommands.UNBIND_TELEGRAM_ID:
                await __unbind_telegram_id(update, context, shared_user.user_id)

            elif current_command == BotCommands.GET_USERS_BY_ID:
                await __get_bound_users_by_tid(update, context, shared_user.user_id)

            elif current_command in (BotCommands.GET_CONFIG, BotCommands.GET_QRCODE):
                await __get_configuration(update, current_command, shared_user.user_id)

            elif current_command == BotCommands.SEND_CONFIG:
                await __send_config(update, context, shared_user)

    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        if update.message is not None:
            await update.message.reply_text(
                "Произошла неожиданная ошибка. Пожалуйста, попробуйте еще раз позже."
            )
    finally:
        if clear_command_flag:
            await __end_command(update, context)


# ---------------------- Вспомогательные функции ----------------------


async def __get_config_buttons_handler(update: Update, context: CallbackContext) -> bool:
    """
    Обработка нажатия кнопок (Own Config или Wg User Config) для команд get_qrcode / get_config.
    Возвращает True, если нужно прервать дальнейший парсинг handle_text.
    """
    if context.user_data is None:
        return False
        
    if update.message is None:
        return False

    current_command = context.user_data.get("command", None)
    if current_command in (BotCommands.GET_CONFIG, BotCommands.GET_QRCODE):
        await __delete_message(update, context)

        if update.message.text == keyboards.BUTTON_OWN.text and update.effective_user is not None:
            await __get_configuration(update, current_command, update.effective_user.id)
            await __end_command(update, context)
            return True

        elif update.message.text == keyboards.BUTTON_WG_USER_CONFIG.text:
            await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
            return True
    return False


async def __close_button_handler(update: Update, context: CallbackContext) -> bool:
    """
    Обработка кнопки Закрыть (BUTTON_CLOSE).
    Возвращает True, если нужно прервать дальнейший парсинг handle_text.
    """
    if not context.user_data:
        return False
    
    current_command = context.user_data.get("command", None)

    if current_command in (BotCommands.ADD_USER, BotCommands.BIND_USER):
        await __delete_message(update, context)
        user_names = context.user_data["wireguard_users"]
        if update.message is not None:
            await update.message.reply_text(
                (
                    f"Связывание пользователей "
                    f'[{", ".join([f"<code>{name}</code>" for name in sorted(user_names)])}] '
                    f"отменено."
                ),
                parse_mode="HTML",
            )
        return True

    elif current_command in (
        BotCommands.UNBIND_TELEGRAM_ID,
        BotCommands.GET_USERS_BY_ID,
        BotCommands.GET_CONFIG,
        BotCommands.GET_QRCODE,
        BotCommands.SEND_CONFIG,
    ):
        await __delete_message(update, context)
        if update.message is not None:
            await update.message.reply_text("Действие отменено.")
        return True
    return False


async def __delete_message(update: Update, context: CallbackContext) -> None:
    """
    Удаляет последнее сообщение пользователя из чата (обычно нажатую кнопку).
    """
    if update.message is not None:
        try:
            await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
        except TelegramError as e:
            logger.error(f"Не удалось удалить сообщение: {e}")


async def __send_message_to_all(update: Update, context: CallbackContext) -> None:
    """
    Отправляет введённое сообщение всем пользователям, зарегистрированным в БД (get_all_telegram_users).
    Если сообщение не удалось отправить, пользователь удаляется из БД.
    """
    for tid in database.get_all_telegram_users():
        try:
            if update.message is not None:
                await context.bot.send_message(chat_id=tid, text=update.message.text)
            logger.info(f"Сообщение успешно отправлено пользователю {tid}")
        except TelegramError as e:
            logger.error(f"Не удалось отправить сообщение пользователю {tid}: {e}")
            database.delete_telegram_user(tid)
            logger.info(f"Пользователь {tid} был удален из базы данных")


async def __validate_username(update: Update, user_name: str) -> bool:
    """
    Проверяет формат имени пользователя Wireguard (латинские буквы и цифры).
    """
    if not telegram_utils.validate_username(user_name):
        if update.message is not None:
            await update.message.reply_text(
                f"Неверный формат для имени пользователя [{user_name}]. "
                f"Имя пользователя может содержать только латинские буквы и цифры."
            )
        return False
    return True


async def __validate_telegram_id(update: Update, tid: int) -> bool:
    """
    Проверяет корректность Telegram ID (целое число).
    """
    if not telegram_utils.validate_telegram_id(tid):
        if update.message is not None:
            await update.message.reply_text(
                f"Неверный формат для Telegram ID [{tid}]. "
                f"Telegram ID должен быть целым числом."
            )
        return False
    return True


async def __add_user(
    update: Update, context: CallbackContext, user_name: str
) -> Optional[wireguard_utils.FunctionResult]:
    """
    Добавляет пользователя Wireguard. Если успешно, сразу отправляет ему .zip-конфиг.
    """
    if not await __validate_username(update, user_name):
        return None

    add_result = wireguard.add_user(user_name)
    if add_result.status:
        zip_result = wireguard.create_zipfile(user_name)
        if zip_result.status and update.message:
            await update.message.reply_document(document=open(zip_result.description, "rb"))
            wireguard.remove_zipfile(user_name)
            if context.user_data is not None:
                context.user_data["wireguard_users"].append(user_name)
    return add_result


async def __rem_user(
    update: Update, user_name: str
) -> Optional[wireguard_utils.FunctionResult]:
    """
    Удаляет пользователя Wireguard, а также запись о нём из БД (если есть).
    """
    if not await __validate_username(update, user_name):
        return None

    remove_result = wireguard.remove_user(user_name)
    if remove_result.status:
        if await __check_database_state(update):
            if not database.delete_user(user_name):
                logger.error(f"Не удалось удалить информацию о пользователе [{user_name}] из базы данных.")
                if update.message is not None:
                    await update.message.reply_text(
                        f"Не удалось удалить информацию о пользователе [{user_name}] из базы данных."
                    )
            else:
                logger.info(f"Пользователь [{user_name}] удален из базы данных.")
    return remove_result


async def __com_user(
    update: Update, user_name: str
) -> Optional[wireguard_utils.FunctionResult]:
    """
    Комментирует или раскомментирует (блокирует/разблокирует) пользователя Wireguard.
    """
    if not await __validate_username(update, user_name):
        return None
    return wireguard.comment_or_uncomment_user(user_name)


async def __create_list_of_wireguard_users(
    update: Update, context: CallbackContext, user_name: str
) -> Optional[wireguard_utils.FunctionResult]:
    """
    Добавляет существующие user_name в список, чтобы затем связать их с Telegram-пользователем
    (либо отправить конфиг).
    """
    if not await __validate_username(update, user_name):
        return None

    check_result = wireguard.check_user_exists(user_name)
    if check_result.status:
        if context.user_data is not None:
            context.user_data["wireguard_users"].append(user_name)
        return None
    return check_result


async def __unbind_user(update: Update, user_name: str) -> None:
    """
    Отвязывает пользователя Wireguard по его user_name (если есть в БД).
    """
    if not await __validate_username(update, user_name):
        return

    if not await __check_database_state(update):
        return

    if database.user_exists(user_name):
        if database.delete_user(user_name):
            logger.info(f"Пользователь [{user_name}] успешно отвязан.")
            if update.message is not None:
                await update.message.reply_text(f"Пользователь [{user_name}] успешно отвязан.")
        else:
            logger.error(f"Не удалось отвязать пользователя [{user_name}].")
            if update.message is not None:
                await update.message.reply_text(f"Не удалось отвязать пользователя [{user_name}].")
    else:
        logger.info(f"Пользователь [{user_name}] не привязан ни к одному Telegram ID в базе данных.")
        if update.message is not None:
            await update.message.reply_text(
                f"Пользователь [{user_name}] не привязан ни к одному Telegram ID в базе данных."
            )


async def __bind_users(update: Update, context: CallbackContext, tid: int) -> None:
    """
    Привязывает список Wireguard-конфигов из context.user_data['wireguard_users']
    к выбранному Telegram ID (tid).
    """
    if not await __check_database_state(update):
        return

    if context.user_data is None:
        return

    telegram_username = await telegram_utils.get_username_by_id(tid, context)

    for user_name in context.user_data["wireguard_users"]:
        if not database.user_exists(user_name):
            # user_name ещё не привязан к никому
            if database.add_user(tid, user_name):
                logger.info(
                    f"Пользователь [{user_name}] успешно привязан к [{telegram_username} ({tid})]."
                )
                if update.message is not None:
                    await update.message.reply_text(
                        f"Пользователь [{user_name}] успешно "
                        f"привязан к [{telegram_username} ({tid})]."
                    )
            else:
                logger.error(f"Не удалось привязать пользователя [{user_name}].")
                if update.message is not None:
                    await update.message.reply_text(
                        f"Произошла ошибка при сохранении данных [{user_name}] в базу. "
                        f"Операция была отменена."
                    )
        else:
            # user_name уже привязан
            already_tid = database.get_telegram_id_by_user(user_name)[0]
            already_username = await telegram_utils.get_username_by_id(already_tid, context)
            logger.info(
                f"Пользователь [{user_name}] уже прикреплен "
                f"к [{already_username} ({already_tid})] в базе данных."
            )
            if update.message is not None:
                await update.message.reply_text(
                    f"Пользователь [{user_name}] уже прикреплен к "
                    f"[{already_username} ({already_tid})] в базе данных."
                )


async def __unbind_telegram_id(update: Update, context: CallbackContext, tid: int) -> None:
    """
    Отвязывает все Wireguard-конфиги от Telegram ID (tid).
    """
    if not await __validate_telegram_id(update, tid):
        return

    if not await __check_database_state(update):
        return

    telegram_username = await telegram_utils.get_username_by_id(tid, context)

    if database.telegram_id_exists(tid):
        if database.delete_users_by_telegram_id(tid):
            logger.info(
                f"Пользователи Wireguard успешно отвязаны от [{telegram_username} ({tid})]."
            )
            if update.message is not None:
                await update.message.reply_text(
                    f"Пользователи Wireguard успешно отвязаны "
                    f"от [{telegram_username} ({tid})]."
                )
        else:
            logger.info(
                f"Не удалось отвязать пользователей Wireguard от [{telegram_username} ({tid})]."
            )
            if update.message is not None:
                await update.message.reply_text(
                    f"Не удалось отвязать пользователей Wireguard "
                    f"от [{telegram_username} ({tid})]."
                )
    else:
        logger.info(
                f"Ни один из пользователей Wireguard не прикреплен "
                f"к [{telegram_username} ({tid})] в базе данных."
            )
        if update.message is not None:
            await update.message.reply_text(
                f"Ни один из пользователей Wireguard не прикреплен "
                f"к [{telegram_username} ({tid})] в базе данных."
            )


async def __get_bound_users_by_tid(update: Update, context: CallbackContext, tid: int) -> None:
    """
    Показывает, какие user_name привязаны к Telegram ID (tid).
    """
    if not await __validate_telegram_id(update, tid):
        return

    if not await __check_database_state(update):
        return

    telegram_username = await telegram_utils.get_username_by_id(tid, context)

    if database.telegram_id_exists(tid):
        user_names = database.get_users_by_telegram_id(tid)
        if update.message is not None:
            await update.message.reply_text(
                f"Пользователи Wireguard, прикрепленные к [{telegram_username} ({tid})]: "
                f"[{', '.join([f'<code>{u}</code>' for u in sorted(user_names)])}].",
                parse_mode="HTML",
            )
    else:
        logger.info(
                f"Ни один из пользователей Wireguard не прикреплен "
                f"к [{telegram_username} ({tid})] в базе данных."
            )
        if update.message is not None:
            await update.message.reply_text(
                f"Ни один из пользователей Wireguard не прикреплен "
                f"к [{telegram_username} ({tid})] в базе данных."
            )


async def __send_config(update: Update, context: CallbackContext, telegram_user: SharedUser) -> None:
    """
    Администратор отправляет пользователю (telegram_user) zip-файлы и QR-коды
    для списка конфигов из context.user_data['wireguard_users'].
    """
    if not await __check_database_state(update):
        return
    
    if context.user_data is None:
        return

    tid = telegram_user.user_id
    telegram_username = telegram_user.username or "NoUsername"

    for user_name in context.user_data["wireguard_users"]:
        check_result = wireguard.check_user_exists(user_name)
        if not check_result.status:
            logger.error(f"Конфиг [{user_name}] не найден.")
            if update.message is not None:
                await update.message.reply_text(f"Конфигурация [{user_name}] не найдена.")
            return

        if wireguard.is_username_commented(user_name):
            logger.info(f"Конфиг [{user_name}] на данный момент закомментирован.")
            if update.message is not None:
                await update.message.reply_text(
                    f"Конфигурация [{user_name}] на данный момент заблокирована."
                )
            return

        logger.info(
            f"Создаю и отправляю Zip-архив и Qr-код пользователя Wireguard [{user_name}] "
            f"пользователю [@{telegram_username} ({tid})]."
        )
        zip_result = wireguard.create_zipfile(user_name)
        try:
            if zip_result.status:
                await context.bot.send_message(chat_id=tid, text="Ваш новый конфиг Wireguard.")
                await context.bot.send_document(chat_id=tid, document=open(zip_result.description, "rb"))
                wireguard.remove_zipfile(user_name)

                png_path = wireguard.get_qrcode_path(user_name)
                if png_path.status:
                    await context.bot.send_photo(chat_id=tid, photo=open(png_path.description, "rb"))

                current_admin_id = -1
                current_admin_name = "NoUsername"
                
                if update.effective_user is not None:
                    current_admin_id = update.effective_user.id
                    current_admin_name = await telegram_utils.get_username_by_id(current_admin_id, context)

                # Оповещаем админов о действии
                text = (
                    f"Администратор [{current_admin_name} ({current_admin_id})] отправил "
                    f"файлы конфигурации Wireguard [{user_name}] пользователю "
                    f"[@{telegram_username} ({tid})]."
                )
                for admin_id in config.telegram_admin_ids:
                    if admin_id == current_admin_id:
                        continue
                    try:
                        await context.bot.send_message(chat_id=admin_id, text=text)
                        logger.info(f"Сообщение для [{admin_id}]: {text}")
                    except TelegramError as e:
                        logger.error(f"Не удалось отправить сообщение администратору {admin_id}: {e}.")
                        if update.message is not None:
                            await update.message.reply_text(
                                f"Не удалось отправить сообщение администратору {admin_id}: {e}."
                            )

        except TelegramError as e:
            logger.error(f"Не удалось отправить сообщение пользователю {tid}: {e}.")
            if update.message is not None:
                await update.message.reply_text(f"Не удалось отправить сообщение пользователю {tid}: {e}.")


# ---------------------- Обработчик ошибок ----------------------


async def error_handler(update: object, context: CallbackContext) -> None:
    """
    Универсальный обработчик ошибок в боте.
    """
    try:
        if context.error is not None:
            raise context.error
    except TimedOut:
        logger.error("Request timed out. Retrying...")
    except BadRequest as e:
        logger.error(f"Bad request: {e}")
    except NetworkError:
        logger.error("Network error occurred. Retrying...")
    except RetryAfter as e:
        logger.error(f"Rate limit exceeded. Retry in {e.retry_after} seconds.")


# ---------------------- Точка входа в приложение ----------------------


def main() -> None:
    """
    Инициализация и запуск Telegram-бота (Long Polling).
    """
    token = config.telegram_token

    # Устанавливаем расписание перезагрузок Wireguard
    # Запускаем планировщик в отдельном потоке
    scheduler_thread = threading.Thread(target=setup_scheduler, daemon=True)
    # scheduler_thread.start()

    application = (
        ApplicationBuilder()
        .token(token)
        .read_timeout(7)                 # Максимальное время ожидания ответа от сервера Telegram
        .write_timeout(10)               # Максимальное время на запись данных (например, при загрузке файлов)
        .connect_timeout(5)              # Максимальное время ожидания при установке соединения
        .pool_timeout(1)                 # Максимальное время ожидания подключения из пула
        .get_updates_read_timeout(30)    # Время ожидания при использовании Long Polling
        .build()
    )

    # Базовые команды
    application.add_handler(CommandHandler(BotCommands.START, start_command))
    application.add_handler(CommandHandler(BotCommands.HELP, help_command))
    application.add_handler(CommandHandler(BotCommands.MENU, menu_command))
    application.add_handler(CommandHandler(BotCommands.CANCEL, cancel_command))

    # Команды управления пользователями Wireguard
    application.add_handler(CommandHandler(BotCommands.ADD_USER, add_user_command))
    application.add_handler(CommandHandler(BotCommands.REMOVE_USER, remove_user_command))
    application.add_handler(CommandHandler(BotCommands.COM_UNCOM_USER, com_uncom_user_command))
    application.add_handler(CommandHandler(BotCommands.SHOW_USERS_STATE, show_users_state_command))

    # Команды управления привязкой пользователей
    application.add_handler(CommandHandler(BotCommands.BIND_USER, bind_user_command))
    application.add_handler(CommandHandler(BotCommands.UNBIND_USER, unbind_user_command))
    application.add_handler(CommandHandler(BotCommands.UNBIND_TELEGRAM_ID, unbind_telegram_id_command))
    application.add_handler(CommandHandler(BotCommands.GET_USERS_BY_ID, get_bound_users_by_telegram_id_command))
    application.add_handler(CommandHandler(BotCommands.SHOW_ALL_BINDINGS, show_all_bindings_command))

    # Команды конфигурации
    application.add_handler(CommandHandler(BotCommands.GET_CONFIG, get_config_command))
    application.add_handler(CommandHandler(BotCommands.GET_QRCODE, get_qrcode_command))
    application.add_handler(CommandHandler(BotCommands.REQUEST_NEW_CONFIG, request_new_config_command))
    application.add_handler(CommandHandler(BotCommands.SEND_CONFIG, send_config_command))

    # Команды для телеграм-пользователей
    application.add_handler(CommandHandler(BotCommands.GET_TELEGRAM_ID, get_telegram_id_command))
    application.add_handler(CommandHandler(BotCommands.GET_TELEGRAM_USERS, get_telegram_users_command))
    application.add_handler(CommandHandler(BotCommands.SEND_MESSAGE, send_message_command))

    # Команды для получения статистики по Wireguard
    application.add_handler(CommandHandler(BotCommands.GET_MY_STATS, get_my_stats_command))
    application.add_handler(CommandHandler(BotCommands.GET_ALL_STATS, get_all_stats_command))

    # Перезагрузка сервера
    application.add_handler(CommandHandler(BotCommands.RELOAD_WG_SERVER, reload_wireguard_server_command))

    # Обработка сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.StatusUpdate.USER_SHARED, handle_user_request))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Обработчик ошибок
    application.add_error_handler(error_handler)

    # Запуск бота
    application.run_polling(timeout=10)


if __name__ == "__main__":
    try:
        if not database.db_loaded:
            logger.error(f"Не удалось подключиться к базе данных: [{config.users_database_path}]!")
        else:
            main()
    except Exception as e:
        logger.error(f"Произошла ошибка: [{e}]")
