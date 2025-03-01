import os
import inspect
import logging
import asyncio
import threading

from telegram import Update
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

from libs.core import config
from libs.core import RotatingCharFileHandler

from libs.wireguard import utils as wireguard_utils

from libs.telegram.types import *
from libs.telegram.database import UserDatabase
from libs.telegram import wrappers, keyboards
from libs.telegram.commands import BotCommands, BotCommandHandler



logger_fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(
    format=logger_fmt,
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Добавляем кастомный обработчик
file_handler = RotatingCharFileHandler(
    base_filename=os.path.join(config.logs_dir, config.base_log_filename),
    max_chars=config.max_log_length
)
file_handler.setFormatter(logging.Formatter(logger_fmt))
logger.addHandler(file_handler)


database = UserDatabase(config.users_database_path)
semaphore = asyncio.Semaphore(config.telegram_max_concurrent_messages)

TELEGRAM_USER_IDS_CACHE: set[TelegramId]
TELEGRAM_USER_IDS_CACHE = set()


command_handler = BotCommandHandler(
    config=config,
    database=database,
    semaphore=semaphore,
    telegram_user_ids_cache=TELEGRAM_USER_IDS_CACHE
)


# ---------------------- Команды бота ----------------------

@wrappers.check_user_not_blocked(lambda: TELEGRAM_USER_IDS_CACHE)
async def unknown_command(update: Update, context: CallbackContext) -> None:
    """
    Обработчик неизвестных команд.
    """
    await command_handler.command(
        BotCommands.UNKNOWN
    ).execute(update, context)
    

async def start_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /start: приветствие и первичная регистрация пользователя в базе.
    """
    await command_handler.command(
        BotCommands.START
    ).execute(update, context)


@wrappers.check_user_not_blocked(lambda: TELEGRAM_USER_IDS_CACHE)
async def help_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /help: показывает помощь по доступным командам.
    """
    await command_handler.command(
        BotCommands.HELP
    ).execute(update, context)


@wrappers.check_user_not_blocked(lambda: TELEGRAM_USER_IDS_CACHE)
async def menu_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /menu: выводит меню в зависимости от прав пользователя.
    """
    await command_handler.command(
        BotCommands.MENU
    ).execute(update, context)


@wrappers.check_user_not_blocked(lambda: TELEGRAM_USER_IDS_CACHE)
async def get_telegram_id_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_telegram_id: выводит телеграм-ID пользователя.
    """
    await command_handler.command(
        BotCommands.GET_TELEGRAM_ID
    ).execute(update, context)


@wrappers.check_user_not_blocked(lambda: TELEGRAM_USER_IDS_CACHE)
async def request_new_config_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /request_new_config: пользователь запрашивает у админов новый конфиг.
    """
    await command_handler.command(
        BotCommands.REQUEST_NEW_CONFIG
    ).execute(update, context)


@wrappers.check_user_not_blocked(lambda: TELEGRAM_USER_IDS_CACHE)
@wrappers.command_lock
async def get_config_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_config: выдаёт пользователю .zip конфигурации Wireguard.
    Если пользователь администратор — позволяет выбрать, чьи конфиги получать.
    """
    await command_handler.command(
        BotCommands.GET_CONFIG
    ).request_input(update, context)


@wrappers.check_user_not_blocked(lambda: TELEGRAM_USER_IDS_CACHE)
@wrappers.command_lock
async def get_qrcode_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_qrcode: выдаёт пользователю QR-код конфигурации Wireguard.
    Если пользователь администратор — позволяет выбрать, чьи QR-коды получать.
    """
    await command_handler.command(
        BotCommands.GET_QRCODE
    ).request_input(update, context)

@wrappers.admin_required
async def get_telegram_users_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_telegram_users: выводит всех телеграм-пользователей, которые
    взаимодействовали с ботом (есть в БД).
    """
    await command_handler.command(
        BotCommands.GET_USERS_BY_ID
    ).execute(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def add_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /add_user: добавляет нового пользователя Wireguard.
    """
    await command_handler.command(
        BotCommands.ADD_USER
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def remove_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /remove_user: удаляет существующего пользователя Wireguard.
    """
    await command_handler.command(
        BotCommands.REMOVE_USER
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def com_uncom_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /com_uncom_user: комментирует/раскомментирует (блокирует/разблокирует)
    пользователей Wireguard (путём комментирования в конфиге).
    """
    await command_handler.command(
        BotCommands.COM_UNCOM_USER
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def bind_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /bind_user: привязывает существующие конфиги Wireguard к Telegram-пользователю.
    """
    await command_handler.command(
        BotCommands.BIND_USER
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def unbind_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /unbind_user: отвязывает конфиги Wireguard от Telegram-пользователя (по user_name).
    """
    await command_handler.command(
        BotCommands.UNBIND_USER
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def send_message_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /send_message: рассылает произвольное сообщение всем зарегистрированным в БД.
    """
    await command_handler.command(
        BotCommands.SEND_MESSAGE
    ).request_input(update, context)


@wrappers.admin_required
async def cancel_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /cancel: универсальная отмена действия для администратора.
    """
    await command_handler.command(
        BotCommands.CANCEL
    ).execute(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def unbind_telegram_id_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /unbind_telegram_id: отвязывает все конфиги Wireguard по конкретному Telegram ID.
    """
    await command_handler.command(
        BotCommands.UNBIND_TELEGRAM_ID
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def get_bound_users_by_telegram_id_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_users_by_id: показать, какие конфиги Wireguard привязаны к Telegram ID.
    """
    await command_handler.command(
        BotCommands.GET_USERS_BY_ID
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def send_config_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /send_config: администратор отправляет конкретные конфиги Wireguard выбранным пользователям.
    """
    await command_handler.command(
        BotCommands.SEND_CONFIG
    ).request_input(update, context)


@wrappers.admin_required
async def show_users_state_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /show_users_state: отображает состояние пользователей (активные/отключённые).
    """
    await command_handler.command(
        BotCommands.SHOW_USERS_STATE
    ).execute(update, context)


@wrappers.admin_required
async def show_all_bindings_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /show_all_bindings: показывает все привязки:
    - Какие пользователи Wireguard привязаны к каким Telegram ID,
    - Список непривязанных Telegram ID,
    - Список непривязанных user_name.
    """
    await command_handler.command(
        BotCommands.SHOW_ALL_BINDINGS
    ).execute(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def ban_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /ban_telegram_user: блокирует пользователя Telegram (игнорирует его сообщения) 
    и комментирует его файлы конфигурации Wireguard.
    """    
    await command_handler.command(
        BotCommands.BAN_TELEGRAM_USER
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def unban_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /unban_telegram_user: разблокирует пользователя Telegram 
    и раскомментирует его файлы конфигурации Wireguard.
    """    
    await command_handler.command(
        BotCommands.UNBAN_TELEGRAM_USER
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def remove_telegram_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /remove_telegram_user: удаляет пользователя Telegram 
    вместе с его файлами конфигурации Wireguard.
    """    
    await command_handler.command(
        BotCommands.REMOVE_TELEGRAM_USER
    ).request_input(update, context)
        

@wrappers.check_user_not_blocked(lambda: TELEGRAM_USER_IDS_CACHE)
async def get_my_stats_command(update: Update, context: CallbackContext) -> None:
    """
    Команда для пользователей (доступна всем).
    Выводит статистику по конфигам WireGuard, привязанным к текущему Telegram ID.
    Если конфиг недоступен или отсутствует (удалён), информация об этом
    выводится в сообщении. При необходимости лишние записи удаляются из БД.
    """
    await command_handler.command(
        BotCommands.GET_MY_STATS
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def get_user_stats_command(update: Update, context: CallbackContext) -> None:
    """
    Команда для администраторов.
    Выводит статистику для конкретного пользователя телеграмм или конкретного конфига WireGuard.
    """
    await command_handler.command(
        BotCommands.GET_USER_STATS
    ).request_input(update, context)


@wrappers.admin_required
async def get_all_stats_command(update: Update, context: CallbackContext) -> None:
    """
    Команда для администраторов.
    Выводит статистику для всех конфигов WireGuard, включая информацию о владельце
    (Telegram ID и username). Если владелец не привязан, выводит соответствующую пометку.
    """
    await command_handler.command(
        BotCommands.GET_ALL_STATS
    ).request_input(update, context)


@wrappers.admin_required
async def reload_wireguard_server_command(update: Update, context: CallbackContext) -> None:
    """
    Обработчик команды перезагрузки сервера Wireguard.
    """
    await command_handler.command(
        BotCommands.RELOAD_WG_SERVER
    ).execute(update, context)

# ---------------------- Обработка входящих сообщений ----------------------

async def handle_update(update: Update, context: CallbackContext, delete_msg: bool = False) -> None:
    """
    Универсальный обработчик входящих сообщений.
    Если delete_msg=True, удаляет сообщение перед обработкой.
    """
    try:
        if delete_msg:
            await __delete_message(update, context)
        
        if context.user_data is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Context user_data is None в функции {curr_frame.f_code.co_name}')
            return
        
        if update.message is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
            return
        
        current_command = context.user_data.get("command")
        
        # Если нет команды, предлагаем меню
        if not current_command:
            await __send_menu(update)
            return

        # Если требуется перезапуск WireGuard после изменений
        if await command_handler.command(current_command).execute(update, context):
            threading.Thread(target=wireguard_utils.log_and_restart_wireguard, daemon=True).start()
    
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        if update.message is not None:
            await update.message.reply_text(
                "Произошла неожиданная ошибка. Пожалуйста, попробуйте еще раз позже."
            )


async def handle_text(update: Update, context: CallbackContext) -> None:
    """
    Обработчик текстовых сообщений, в которых пользователи вводят имена
    пользователей Wireguard или другие данные после команды.
    """
    await handle_update(update, context)


async def handle_user_request(update: Update, context: CallbackContext) -> None:
    """
    Обработчик, который срабатывает, когда пользователь шлёт запрос
    с кнопкой выбора Telegram-пользователя (filters.StatusUpdate.USER_SHARED).
    """
    await handle_update(update, context)

# ---------------------- Вспомогательные функции ----------------------

async def __delete_message(update: Update, context: CallbackContext) -> None:
    """
    Удаляет последнее сообщение пользователя из чата (обычно нажатую кнопку).
    """
    if update.message is not None:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id,message_id=update.message.message_id
            )
        except TelegramError as e:
            logger.error(f"Не удалось удалить сообщение: {e}")
            

async def __send_menu(update: Update) -> None:
    """
    Отправляет меню с кнопками в зависимости от прав пользователя.
    """
    if update.effective_user is not None and update.message is not None:
        await update.message.reply_text(
            f"Пожалуйста, выберите команду из меню. (/{BotCommands.MENU})",
            reply_markup=(
                keyboards.ADMIN_MENU if update.effective_user.id in config.telegram_admin_ids else keyboards.USER_MENU
            )
        )

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

# ---------------------- Планировщик перезагрузок Wireguard сервера ----------------------

def __setup_scheduler():
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
        success = await wireguard_utils.async_restart_wireguard()
        logger.info(f"Перезагрузка прошла: {'успешно' if success else 'неудачно'}!")
    except Exception as e:
        logger.error(f"Ошибка в расписании: {str(e)}")

# ---------------------- Точка входа в приложение ----------------------


def main() -> None:
    """
    Инициализация и запуск Telegram-бота (Long Polling).
    """
    token = config.telegram_token

    # Устанавливаем расписание перезагрузок Wireguard
    # Запускаем планировщик в отдельном потоке
    scheduler_thread = threading.Thread(target=__setup_scheduler, daemon=True)
    scheduler_thread.start()

    # Загружаем текущих пользователей Telegram в кэш
    global TELEGRAM_USER_IDS_CACHE
    TELEGRAM_USER_IDS_CACHE = set([
        tid for tid, ban_status in database.get_all_telegram_users() if not ban_status
    ])

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

    application.add_handler(CommandHandler(BotCommands.BAN_TELEGRAM_USER, ban_user_command))
    application.add_handler(CommandHandler(BotCommands.UNBAN_TELEGRAM_USER, unban_user_command))
    application.add_handler(CommandHandler(BotCommands.REMOVE_TELEGRAM_USER, remove_telegram_user_command))

    # Команды для получения статистики по Wireguard
    application.add_handler(CommandHandler(BotCommands.GET_MY_STATS, get_my_stats_command))
    application.add_handler(CommandHandler(BotCommands.GET_USER_STATS, get_user_stats_command))
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
