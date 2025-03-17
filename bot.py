import os
import inspect
import logging
import asyncio
import threading
from typing import Awaitable, Callable, Dict, Set

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
from libs.telegram.commands import BotCommand, BotCommandHandler, ContextDataKeys



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


user_database = UserDatabase(config.users_database_path)
telegram_message_semaphore = asyncio.Semaphore(config.telegram_max_concurrent_messages)

telegram_user_ids_cache: Set[TelegramId] = set()

bot_command_handler: BotCommandHandler

# Определяем тип для асинхронных функций-обработчиков, которые принимают 
# update и context и возвращают coroutine с результатом None.
HandlerFunc = Callable[[Update, CallbackContext], Awaitable[None]]
text_command_handlers: Dict[str, HandlerFunc] = {}


# ---------------------- Команды бота ----------------------

@wrappers.check_user_not_blocked(lambda: telegram_user_ids_cache)
async def unknown_command(update: Update, context: CallbackContext) -> None:
    """
    Обработчик неизвестных команд.
    """
    await bot_command_handler.command(
        BotCommand.UNKNOWN
    ).execute(update, context)
    

async def start_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /start: приветствие и первичная регистрация пользователя в базе.
    """
    await bot_command_handler.command(
        BotCommand.START
    ).execute(update, context)


@wrappers.check_user_not_blocked(lambda: telegram_user_ids_cache)
async def help_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /help: показывает помощь по доступным командам.
    """
    await bot_command_handler.command(
        BotCommand.HELP
    ).execute(update, context)


@wrappers.check_user_not_blocked(lambda: telegram_user_ids_cache)
async def menu_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /menu: выводит меню в зависимости от прав пользователя.
    """
    await bot_command_handler.command(
        BotCommand.MENU
    ).execute(update, context)


@wrappers.check_user_not_blocked(lambda: telegram_user_ids_cache)
async def get_telegram_id_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_telegram_id: выводит телеграм-ID пользователя.
    """
    await bot_command_handler.command(
        BotCommand.GET_TELEGRAM_ID
    ).execute(update, context)


@wrappers.check_user_not_blocked(lambda: telegram_user_ids_cache)
async def request_new_config_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /request_new_config: пользователь запрашивает у админов новый конфиг.
    """
    await bot_command_handler.command(
        BotCommand.REQUEST_NEW_CONFIG
    ).execute(update, context)


@wrappers.check_user_not_blocked(lambda: telegram_user_ids_cache)
@wrappers.command_lock
async def get_config_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_config: выдаёт пользователю .zip конфигурации Wireguard.
    Если пользователь администратор — позволяет выбрать, чьи конфиги получать.
    """
    await bot_command_handler.command(
        BotCommand.GET_CONFIG
    ).request_input(update, context)


@wrappers.check_user_not_blocked(lambda: telegram_user_ids_cache)
@wrappers.command_lock
async def get_qrcode_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_qrcode: выдаёт пользователю QR-код конфигурации Wireguard.
    Если пользователь администратор — позволяет выбрать, чьи QR-коды получать.
    """
    await bot_command_handler.command(
        BotCommand.GET_QRCODE
    ).request_input(update, context)

@wrappers.admin_required
async def get_telegram_users_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_telegram_users: выводит всех телеграм-пользователей, которые
    взаимодействовали с ботом (есть в БД).
    """
    await bot_command_handler.command(
        BotCommand.GET_TELEGRAM_USERS
    ).execute(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def add_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /add_user: добавляет нового пользователя Wireguard.
    """
    await bot_command_handler.command(
        BotCommand.ADD_USER
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def remove_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /remove_user: удаляет существующего пользователя Wireguard.
    """
    await bot_command_handler.command(
        BotCommand.REMOVE_USER
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def com_uncom_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /com_uncom_user: комментирует/раскомментирует (блокирует/разблокирует)
    пользователей Wireguard (путём комментирования в конфиге).
    """
    await bot_command_handler.command(
        BotCommand.COM_UNCOM_USER
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def bind_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /bind_user: привязывает существующие конфиги Wireguard к Telegram-пользователю.
    """
    await bot_command_handler.command(
        BotCommand.BIND_USER
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def unbind_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /unbind_user: отвязывает конфиги Wireguard от Telegram-пользователя (по user_name).
    """
    await bot_command_handler.command(
        BotCommand.UNBIND_USER
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def send_message_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /send_message: рассылает произвольное сообщение всем зарегистрированным в БД.
    """
    await bot_command_handler.command(
        BotCommand.SEND_MESSAGE
    ).request_input(update, context)


@wrappers.admin_required
async def cancel_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /cancel: универсальная отмена действия для администратора.
    """
    await bot_command_handler.command(
        BotCommand.CANCEL
    ).execute(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def unbind_telegram_id_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /unbind_telegram_id: отвязывает все конфиги Wireguard по конкретному Telegram ID.
    """
    await bot_command_handler.command(
        BotCommand.UNBIND_TELEGRAM_ID
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def get_bound_users_by_telegram_id_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /get_users_by_id: показать, какие конфиги Wireguard привязаны к Telegram ID.
    """
    await bot_command_handler.command(
        BotCommand.GET_USERS_BY_ID
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def send_config_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /send_config: администратор отправляет конкретные конфиги Wireguard выбранным пользователям.
    """
    await bot_command_handler.command(
        BotCommand.SEND_CONFIG
    ).request_input(update, context)


@wrappers.admin_required
async def show_users_state_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /show_users_state: отображает состояние пользователей (активные/отключённые).
    """
    await bot_command_handler.command(
        BotCommand.SHOW_USERS_STATE
    ).execute(update, context)


@wrappers.admin_required
async def show_all_bindings_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /show_all_bindings: показывает все привязки:
    - Какие пользователи Wireguard привязаны к каким Telegram ID,
    - Список непривязанных Telegram ID,
    - Список непривязанных user_name.
    """
    await bot_command_handler.command(
        BotCommand.SHOW_ALL_BINDINGS
    ).execute(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def ban_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /ban_telegram_user: блокирует пользователя Telegram (игнорирует его сообщения) 
    и комментирует его файлы конфигурации Wireguard.
    """    
    await bot_command_handler.command(
        BotCommand.BAN_TELEGRAM_USER
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def unban_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /unban_telegram_user: разблокирует пользователя Telegram 
    и раскомментирует его файлы конфигурации Wireguard.
    """    
    await bot_command_handler.command(
        BotCommand.UNBAN_TELEGRAM_USER
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def remove_telegram_user_command(update: Update, context: CallbackContext) -> None:
    """
    Команда /remove_telegram_user: удаляет пользователя Telegram 
    вместе с его файлами конфигурации Wireguard.
    """    
    await bot_command_handler.command(
        BotCommand.REMOVE_TELEGRAM_USER
    ).request_input(update, context)
        

@wrappers.check_user_not_blocked(lambda: telegram_user_ids_cache)
async def get_my_stats_command(update: Update, context: CallbackContext) -> None:
    """
    Команда для пользователей (доступна всем).
    Выводит статистику по конфигам WireGuard, привязанным к текущему Telegram ID.
    Если конфиг недоступен или отсутствует (удалён), информация об этом
    выводится в сообщении. При необходимости лишние записи удаляются из БД.
    """
    await bot_command_handler.command(
        BotCommand.GET_MY_STATS
    ).request_input(update, context)


@wrappers.admin_required
@wrappers.command_lock
async def get_user_stats_command(update: Update, context: CallbackContext) -> None:
    """
    Команда для администраторов.
    Выводит статистику для конкретного пользователя телеграмм или конкретного конфига WireGuard.
    """
    await bot_command_handler.command(
        BotCommand.GET_USER_STATS
    ).request_input(update, context)


@wrappers.admin_required
async def get_all_stats_command(update: Update, context: CallbackContext) -> None:
    """
    Команда для администраторов.
    Выводит статистику для всех конфигов WireGuard, включая информацию о владельце
    (Telegram ID и username). Если владелец не привязан, выводит соответствующую пометку.
    """
    await bot_command_handler.command(
        BotCommand.GET_ALL_STATS
    ).execute(update, context)


@wrappers.admin_required
async def reload_wireguard_server_command(update: Update, context: CallbackContext) -> None:
    """
    Обработчик команды перезагрузки сервера Wireguard.
    """
    await bot_command_handler.command(
        BotCommand.RELOAD_WG_SERVER
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
            await __send_menu(update, context)
            return

        # Если требуется перезапуск WireGuard после изменений
        if await bot_command_handler.command(current_command).execute(update, context):
            threading.Thread(target=wireguard_utils.log_and_restart_wireguard, daemon=True).start()
    
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        if update.message is not None:
            await update.message.reply_text(
                "Произошла неожиданная ошибка. Пожалуйста, попробуйте еще раз позже."
            )


async def handle_command(update: Update, context: CallbackContext) -> None:
    """
    Обработчик команд, отправленных пользователем.
    """
    if update.message is not None and update.message.text is not None:
        await text_command_handlers[
            BotCommand.from_command(update.message.text).pretty_text
        ](update, context)


async def handle_text(update: Update, context: CallbackContext) -> None:
    """
    Обработчик текстовых сообщений, в которых пользователи вводят имена
    пользователей WireGuard или другие данные после команды.
    
    Если введенный текст соответствует одной из зарегистрированных текстовых команд,
    вызывается соответствующий обработчик.
    В противном случае сообщение передается в общий обработчик.
    """
    if update.message is None or context.user_data is None:
        return
    
    if update.message.text is None:
        return
        
    # Если для пользователя не установлено текущее меню, то устанавливаем главное
    if context.user_data.get(ContextDataKeys.CURRENT_MENU) is None:
        if update.effective_user is not None:
            user_id = update.effective_user.id
            keyboard = (
                keyboards.KEYBOARD_MANAGER.get_admin_main_keyboard()
                if user_id in config.telegram_admin_ids
                else keyboards.KEYBOARD_MANAGER.get_user_main_keyboard()
            )
            context.user_data[ContextDataKeys.CURRENT_MENU] = keyboard.id
    
    # Не используем else, чтобы пользователю не нужно было снова вводить данные
    # Таким образом мы сразу бесшовно обрабатываем введенные данные и устанавливаем меню
    if context.user_data.get(ContextDataKeys.CURRENT_MENU) is not None:
        current_keyboard = keyboards.KEYBOARD_MANAGER.get_keyboard(
            context.user_data[ContextDataKeys.CURRENT_MENU]
        )
        
        if current_keyboard is None:
            logger.error(
                f'Не удалось получить клавиатуру с id {context.user_data[ContextDataKeys.CURRENT_MENU]}.'
            )
            return
        
        # Если это подменю нашей клавиатуры
        if update.message.text in current_keyboard:
            # Если это кнопка вернуться, то возвращаемся
            if await __turn_back_button_handler(update, context):
                return
            
            # Если это команда, то выполняем ее
            if update.message.text in text_command_handlers:
                await text_command_handlers[update.message.text](update, context)
                return
    
            # В ином случае это подменю
            child_menus = [child for child in current_keyboard.children if child.is_menu is True]
            
            for child_menu in child_menus:
                if update.message.text == child_menu.title:
                    context.user_data[ContextDataKeys.CURRENT_MENU] = child_menu.id
                    await update.message.reply_text(
                        f"Переходим в {child_menu.title}.", reply_markup=child_menu.reply_keyboard
                    )
                    return
    
    await handle_update(update, context)


async def handle_user_request(update: Update, context: CallbackContext) -> None:
    """
    Обработчик, который срабатывает, когда пользователь шлёт запрос
    с кнопкой выбора Telegram-пользователя (filters.StatusUpdate.USER_SHARED).
    """
    await handle_update(update, context, delete_msg=True)

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
            

async def __send_menu(update: Update, context: CallbackContext) -> None:
    """
    Отправляет меню с кнопками в зависимости от прав пользователя.
    """
    if update.effective_user is not None and update.message is not None and context.user_data is not None:
        current_keyboard = keyboards.KEYBOARD_MANAGER.get_keyboard(
            context.user_data[ContextDataKeys.CURRENT_MENU]
        )
        
        if current_keyboard is None:
            logger.error(
                f'Не удалось получить клавиатуру с id'
                f' {context.user_data[ContextDataKeys.CURRENT_MENU]}.'
            )
            current_keyboard = (
                keyboards.KEYBOARD_MANAGER.get_admin_main_keyboard() 
                if update.effective_user.id in config.telegram_admin_ids
                else keyboards.KEYBOARD_MANAGER.get_user_main_keyboard()
            )
        
        await update.message.reply_text(
            f"Пожалуйста, выберите команду из меню. (/{BotCommand.MENU})",
            reply_markup=current_keyboard.reply_keyboard
        )


async def __turn_back_button_handler(update: Update, context: CallbackContext) -> bool:
        """
        Обработка кнопки вернуться назад (ButtonText.TURN_BACK).
        Возвращает True, если нужно прервать дальнейший парсинг handle_text.
        """
        if context.user_data is None:
            return False
        
        if update.message is None or update.message.text != keyboards.ButtonText.TURN_BACK:
            return False
        
        keyboard = keyboards.KEYBOARD_MANAGER.get_keyboard(context.user_data[ContextDataKeys.CURRENT_MENU])
        if keyboard is None:
            logger.error(f'Не удалось найти клавиатуру с индексом {context.user_data[ContextDataKeys.CURRENT_MENU]}')
            return False
        
        prev_keyboard = keyboard.parent if keyboard.parent is not None else keyboard
        context.user_data[ContextDataKeys.CURRENT_MENU] = prev_keyboard.id
        await update.message.reply_text(
            f"Возврат в {prev_keyboard.title}.", reply_markup=prev_keyboard.reply_keyboard
        )
        return True

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
    global telegram_user_ids_cache
    telegram_user_ids_cache = set([
        tid for tid, ban_status in user_database.get_all_telegram_users() if not ban_status
    ])
    
    global bot_command_handler
    bot_command_handler = BotCommandHandler(
        config=config,
        database=user_database,
        semaphore=telegram_message_semaphore,
        telegram_user_ids_cache=telegram_user_ids_cache
    )

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
    
    global text_command_handlers
    text_command_handlers = {
        BotCommand.START.pretty_text: start_command,
        BotCommand.HELP.pretty_text: help_command,
        BotCommand.MENU.pretty_text: menu_command,
        BotCommand.CANCEL.pretty_text: cancel_command,
        BotCommand.UNKNOWN.pretty_text: unknown_command,
        
        BotCommand.ADD_USER.pretty_text: add_user_command,
        BotCommand.REMOVE_USER.pretty_text: remove_user_command,
        BotCommand.COM_UNCOM_USER.pretty_text: com_uncom_user_command,
        BotCommand.SHOW_USERS_STATE.pretty_text: show_users_state_command,

        BotCommand.BIND_USER.pretty_text: bind_user_command,
        BotCommand.UNBIND_USER.pretty_text: unbind_user_command,
        BotCommand.UNBIND_TELEGRAM_ID.pretty_text: unbind_telegram_id_command,
        BotCommand.GET_USERS_BY_ID.pretty_text: get_bound_users_by_telegram_id_command,
        BotCommand.SHOW_ALL_BINDINGS.pretty_text: show_all_bindings_command,

        BotCommand.BAN_TELEGRAM_USER.pretty_text: ban_user_command,
        BotCommand.UNBAN_TELEGRAM_USER.pretty_text: unban_user_command,
        BotCommand.REMOVE_TELEGRAM_USER.pretty_text: remove_telegram_user_command,

        BotCommand.GET_CONFIG.pretty_text: get_config_command,
        BotCommand.GET_QRCODE.pretty_text: get_qrcode_command,
        BotCommand.REQUEST_NEW_CONFIG.pretty_text: request_new_config_command,
        BotCommand.SEND_CONFIG.pretty_text: send_config_command,

        BotCommand.GET_TELEGRAM_ID.pretty_text: get_telegram_id_command,
        BotCommand.GET_TELEGRAM_USERS.pretty_text: get_telegram_users_command,
        BotCommand.SEND_MESSAGE.pretty_text: send_message_command,

        BotCommand.GET_MY_STATS.pretty_text: get_my_stats_command,
        BotCommand.GET_USER_STATS.pretty_text: get_user_stats_command,
        BotCommand.GET_ALL_STATS.pretty_text: get_all_stats_command,

        BotCommand.RELOAD_WG_SERVER.pretty_text: reload_wireguard_server_command,
    }

    # Обработка сообщений
    application.add_handler(MessageHandler(filters.COMMAND, handle_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.StatusUpdate.USER_SHARED, handle_user_request))

    # Обработчик ошибок
    application.add_error_handler(error_handler)

    # Запуск бота
    application.run_polling(timeout=10)


if __name__ == "__main__":
    try:
        if not user_database.db_loaded:
            logger.error(f"Не удалось подключиться к базе данных: [{config.users_database_path}]!")
        else:
            main()
    except Exception as e:
        logger.error(f"Произошла ошибка: [{e}]")
