import logging
import asyncio
from typing import Optional

from telegram import Update, UsersShared, ReplyKeyboardRemove# type: ignore
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackContext, filters# type: ignore
from telegram.error import TelegramError# type: ignore

from libs.wireguard import config
from libs.wireguard import user_control as wireguard
from libs.wireguard import utils as wireguard_utils

from libs.telegram.database import UserDatabase
from libs.telegram import utils as telegram_utils
from libs.telegram import wrappers, keyboards, messages


# Включаем логирование для отладки
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


database = UserDatabase(config.users_database_path)
semaphore = asyncio.Semaphore(config.telegram_max_concurrent_messages)


async def __check_database_state(update: Update) -> bool:
    if not database.db_loaded:
        logger.error('Ошибка! База данных не загружена!')
        await update.message.reply_text('Технические неполадки. Пожалуйста, свяжитесь с администратором.')
        return False
    return True


async def __ensure_user_exists(telegram_id: int, update: Update) -> bool:
    """
    Проверяет, загружена ли база данных, а затем проверяет, существует ли пользователь в базе данных.
    Если база данных не загружена — возвращает ошибку. Если пользователя нет в базе данных, он будет добавлен.
    
    Args:
        user_id (int): Идентификатор пользователя Telegram.
        update (Update): Объект Update для отправки сообщений пользователю.

    Returns:
        bool: True, если пользователь существует или был добавлен. False, если база данных не загружена.
    """
    if not await __check_database_state(update):
        return False

    if not database.is_telegram_user_exists(telegram_id):
        logger.info(f"Добавляю нового участника Tid [{telegram_id}].")
        database.add_telegram_user(telegram_id)
    return True


# Команда /start
async def start_command(update: Update, context: CallbackContext) -> None:
    telegram_id = update.effective_user.id
    if not await __ensure_user_exists(telegram_id, update):
        return
    
    logger.info(f"Отправляю ответ на команду [start] -> Tid [{telegram_id}].")
    await update.message.reply_text(
        messages.ADMIN_HELLO if telegram_id in config.telegram_admin_ids else messages.USER_HELLO
    )


# Команда /help
async def help_command(update: Update, context: CallbackContext) -> None:
    telegram_id = update.effective_user.id
    if not await __ensure_user_exists(telegram_id, update):
        return
    
    logger.info(f"Отправляю ответ на команду [help] -> Tid [{telegram_id}].")
    await update.message.reply_text(
        messages.ADMIN_HELP if telegram_id in config.telegram_admin_ids else messages.USER_HELP,
        parse_mode='HTML'
    )
    await __end_command(update)


# Команда /menu
async def menu_command(update: Update, context: CallbackContext) -> None:
    telegram_id = update.effective_user.id
    if not await __ensure_user_exists(telegram_id, update):
        return

    logger.info(f"Отправляю ответ на команду [menu] -> Tid [{telegram_id}].")
    await update.message.reply_text(
        'Выберите команду.',
        reply_markup=(
            keyboards.ADMIN_MENU if telegram_id in config.telegram_admin_ids else keyboards.USER_MENU
        )
    )


# Команда /get_telegram_id
async def get_telegram_id_command(update: Update, context: CallbackContext) -> None:
    telegram_id = update.effective_user.id
    if not await __ensure_user_exists(telegram_id, update):
        return
    
    logger.info(f"Отправляю ответ на команду [get_telegram_id] -> Tid [{telegram_id}].")
    await update.message.reply_text(f'Ваш id: {telegram_id}.')
    await __end_command(update)


# Команда /request_new_config
async def request_new_config_command(update: Update, context: CallbackContext) -> None:
    telegram_id = update.effective_user.id
    telegram_name = await telegram_utils.get_username_by_id(telegram_id, context)

    for admin_id in config.telegram_admin_ids:
        try:
            # Отправляем сообщение каждому пользователю
            await context.bot.send_message(chat_id=admin_id, text=
                                           f'Пользователь [{telegram_name} ({telegram_id})] запросил новый конфиг Wireguard.')
            logger.info(
                f"Сообщение о запросе нового конфига пользователем [{telegram_name} ({telegram_id})] отправлено админу {admin_id}.")
        except TelegramError as e:
            logger.error(f"Не удалось отправить сообщение админу {admin_id}: {e}.")

    await __end_command(update)


# Команда /get_telegram_users
@wrappers.admin_required
async def get_telegram_users_command(update: Update, context: CallbackContext) -> None:
    telegram_id = update.effective_user.id

    if not database.db_loaded:
        logger.error('Ошибка! Не база данных не загружена!')
        await update.message.reply_text('Не удалось получить данные из базы данных.')
        return

    telegram_ids = database.get_all_telegram_users()
    logger.info(f"Отправляю список телеграмм пользователей -> Tid [{telegram_id}].")
    if telegram_ids:
        telegram_usernames = await telegram_utils.get_usernames_in_bulk(telegram_ids, context, semaphore)

        # Оформляем заголовок с использованием HTML
        header = f"<b>📋 Telegram Id всех пользователей бота [{len(telegram_ids)}]</b>\n\n"
        user_lines = [
            f"{index}. {telegram_username or 'Нет имени пользователя'} ({telegram_id})\n"
            for index, (telegram_id, telegram_username) in enumerate(telegram_usernames.items(), start=1)
        ]

        # Отправляем сообщение с разметкой HTML
        await update.message.reply_text(header + "".join(user_lines), parse_mode='HTML')

    else:
        await update.message.reply_text(f'У бота пока нет активных Telegram пользователей.')
    await __end_command(update)


# Команда /add_user
@wrappers.admin_required
@wrappers.command_lock
async def add_user_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text((
            'Пожалуйста, введите имена пользователей Wireguard, разделяя их пробелом.\n\n'
            'Чтобы отменить ввод, используйте команду /cancel.'
        ))
    context.user_data['command'] = 'add_user'
    context.user_data['wireguard_users'] = []


# Команда /remove_user
@wrappers.admin_required
@wrappers.command_lock
async def remove_user_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text((
            'Пожалуйста, введите имена пользователей Wireguard, разделяя их пробелом.\n\n'
            'Чтобы отменить ввод, используйте команду /cancel.'
        ))
    context.user_data['command'] = 'remove_user'
    

# Команда /com_uncom_user
@wrappers.admin_required
@wrappers.command_lock
async def com_uncom_user_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text((
            'Пожалуйста, введите имена пользователей, разделяя их пробелом.\n\n'
            'Чтобы отменить ввод, используйте команду /cancel.'
        ))
    context.user_data['command'] = 'com_uncom_user'


# Команда /bind_user
@wrappers.admin_required
@wrappers.command_lock
async def bind_user_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text((
            'Пожалуйста, введите имена пользователей Wireguard, разделяя их пробелом.\n\n'
            'Чтобы отменить ввод, используйте команду /cancel.'
        ))
    context.user_data['command'] = 'bind_user'
    context.user_data['wireguard_users'] = []


# Команда /unbind_user
@wrappers.admin_required
@wrappers.command_lock
async def unbind_user_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text((
            'Пожалуйста, введите имена пользователей Wireguard, разделяя их пробелом.\n\n'
            'Чтобы отменить ввод, используйте команду /cancel.'
        ))
    context.user_data['command'] = 'unbind_user'


# Команда /send_message
@wrappers.admin_required
@wrappers.command_lock
async def send_message_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text((
            'Введите текст для рассылки.\n\n'
            'Чтобы отменить ввод, используйте команду /cancel.'
        ))
    context.user_data['command'] = 'send_message'


# Команда для отмены действия
@wrappers.admin_required
async def cancel_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text((
            'Действие отменено. Можете начать сначала, выбрав команду из меню (/menu).'
        ),
        reply_markup=keyboards.ADMIN_MENU
    )
    context.user_data['command'] = None


# Команда /unbind_telegram_id
@wrappers.admin_required
@wrappers.command_lock
async def unbind_telegram_id_command(update: Update, context: CallbackContext) -> None:    
    await update.message.reply_text((
            'Пожалуйста, выберите пользователя Telegram, которого хотите отвязать.\n\n'
            'Для отмены действия нажмите кнопку Закрыть.'
        ), 
        reply_markup=keyboards.BIND_MENU
    )
    context.user_data['command'] = 'unbind_telegram_id'


# Команда /get_users_by_id
@wrappers.admin_required
@wrappers.command_lock
async def get_bound_users_by_telegram_id_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text((
            'Пожалуйста, выберите пользователя Telegram, привязки которого хотите увидеть.\n\n'
            'Для отмены действия нажмите кнопку Закрыть.'
        ),
        reply_markup=keyboards.BIND_MENU
    )
    context.user_data['command'] = 'get_users_by_id'


@wrappers.admin_required
@wrappers.command_lock
async def send_config_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text((
            'Пожалуйста, введите имена пользователей Wireguard, разделяя их пробелом.\n\n'
            'Чтобы отменить ввод, используйте команду /cancel.'
        ))
    context.user_data['command'] = 'send_config'
    context.user_data['wireguard_users'] = []


# Команда /show_users_state
@wrappers.admin_required
async def show_users_state_command(update: Update, context: CallbackContext) -> None:
    from_telegram_id = update.effective_user.id

    if not database.db_loaded:
        logger.error('Ошибка! Не база данных не загружена!')
        await update.message.reply_text('Не удалось получить данные из базы данных.')
        return

    # Получаем всех пользователей из таблицы linked_users
    linked_users = database.get_all_linked_data()

    # Получаем активных пользователей
    active_usernames = sorted(wireguard.get_active_usernames())

    # Получаем отключенных пользователей
    inactive_usernames = sorted(wireguard.get_inactive_usernames())

    # Словарь для привязанных пользователей: {user_names: telegram_id}
    linked_dict = {}
    for telegram_id, user_name in linked_users:
        linked_dict[user_name] = telegram_id

    active_telegram_ids = [linked_dict.get(user_name, "Нет привязки") for user_name in active_usernames]
    inactive_telegram_ids = [linked_dict.get(user_name, "Нет привязки") for user_name in inactive_usernames]
    active_telegram_names_dict = await telegram_utils.get_usernames_in_bulk(
        [tid for tid in active_telegram_ids if telegram_utils.validate_telegram_id(tid)], context, semaphore)
    inactive_telegram_names_dict = await telegram_utils.get_usernames_in_bulk(
        [tid for tid in inactive_telegram_ids if telegram_utils.validate_telegram_id(tid)], context, semaphore)

    message_parts = []
    message_parts.append(f"<b>🔹 Активные пользователи [{len(active_usernames)}] 🔹</b>\n")
    for index, user_name in enumerate(active_usernames, start=1):
        telegram_id = linked_dict.get(user_name, "Нет привязки")
        telegram_name = active_telegram_names_dict.get(telegram_id, None) or "Нет имени пользователя"
        message_parts.append(f"{index}. <code>{user_name}</code> - {telegram_name} ({telegram_id})\n")

    message_parts.append(f"\n<b>🔹 Отключенные пользователи [{len(inactive_usernames)}] 🔹</b>\n")
    for index, user_name in enumerate(inactive_usernames, start=1):
        telegram_id = linked_dict.get(user_name, "Нет привязки")
        telegram_name = inactive_telegram_names_dict.get(telegram_id, None) or "Нет имени пользователя"
        message_parts.append(f"{index}. <code>{user_name}</code> - {telegram_name} ({telegram_id})\n")

    logger.info(f'Отправляю информацию об активных и отключенных пользователях -> Tid [{from_telegram_id}].')
    # Отправляем сообщение (или несколько, если оно длинное)
    await telegram_utils.send_long_message(update, "".join(message_parts), parse_mode='HTML')
    await __end_command(update)
    

# Команда /show_all_bindings
@wrappers.admin_required
async def show_all_bindings_command(update: Update, context: CallbackContext) -> None:
    from_telegram_id = update.effective_user.id

    if not database.db_loaded:
        logger.error('Ошибка! Не база данных не загружена!')
        await update.message.reply_text('Не удалось получить данные из базы данных.')
        return

    # Получаем всех пользователей из таблицы linked_users
    linked_users = database.get_all_linked_data()

    # Получаем всех пользователей из таблицы telegram_users
    telegram_ids_in_users = database.get_all_telegram_users()

    # Используем функцию для получения всех доступных user_name
    available_usernames = wireguard.get_usernames()

    # Словарь для привязанных пользователей: {telegram_id: [user_names]}
    linked_dict = {}
    for telegram_id, user_name in linked_users:
        if telegram_id in linked_dict:
            linked_dict[telegram_id].append(user_name)
        else:
            linked_dict[telegram_id] = [user_name]

    # Получение usernames привязанных пользователей
    linked_telegram_ids = list(linked_dict.keys())
    linked_telegram_names_dict = await telegram_utils.get_usernames_in_bulk(linked_telegram_ids, context, semaphore)

    # Формирование сообщения для привязанных пользователей
    message_parts = []
    message_parts.append(f"<b>🔹🔐 Привязанные пользователи [{len(linked_dict)}] 🔹</b>\n")
    for index, (telegram_id, user_names) in enumerate(linked_dict.items(), start=1):
        user_names_formatted = ', '.join([f"<code>{user_name}</code>" for user_name in sorted(user_names)])
        telegram_name = linked_telegram_names_dict.get(telegram_id, None) or "Нет имени пользователя"
        message_parts.append(f"{index}. {telegram_name} ({telegram_id}): {user_names_formatted}\n")

    # Определение непривязанных Telegram ID
    unlinked_telegram_ids = set(telegram_ids_in_users) - set(linked_telegram_ids)
    if unlinked_telegram_ids:
        unlinked_telegram_names_dict = await telegram_utils.get_usernames_in_bulk(unlinked_telegram_ids, context, semaphore)
        message_parts.append(f"\n<b>🔹❌ Непривязанные Telegram Id [{len(unlinked_telegram_ids)}] 🔹</b>\n")
        for index, telegram_id in enumerate(unlinked_telegram_ids, start=1):
            telegram_name = unlinked_telegram_names_dict.get(telegram_id, None) or "Нет имени пользователя"
            message_parts.append(f"{index}. {telegram_name} ({telegram_id})\n")

    # Определение непривязанных user_name
    linked_usernames = {user_name for _, user_name in linked_users}
    unlinked_usernames = set(available_usernames) - linked_usernames
    if unlinked_usernames:
        message_parts.append(f"\n<b>🔹🛡️ Непривязанные конфиги Wireguard [{len(unlinked_usernames)}] 🔹</b>\n")
        for index, user_name in enumerate(sorted(unlinked_usernames), start=1):
            message_parts.append(f"{index}. <code>{user_name}</code>\n")

    logger.info(f'Отправляю информацию о привязанных и непривязанных пользователях -> Tid [{from_telegram_id}].')
    # Отправляем сообщение (или несколько, если оно длинное)
    await telegram_utils.send_long_message(update, "".join(message_parts), parse_mode='HTML')
    await __end_command(update)


async def __get_configuration(update: Update, command: str, telegram_id: int) -> None:
    requester_telegram_id = update.effective_user.id

    if not database.db_loaded:
        logger.error('Ошибка! Не база данных не загружена!')
        await update.message.reply_text('Не удалось получить данные из базы данных. Пожалуйста, свяжитесь с администратором.')
        return
    
    if requester_telegram_id == telegram_id:
        if not database.is_telegram_user_exists(telegram_id):
            logger.info(f'Добавляю пользователя Tid [{telegram_id}] в базу данных.')
            database.add_telegram_user(telegram_id)

    user_names = database.get_users_by_telegram_id(telegram_id)

    if not user_names:
        logger.info(f'Пользователь Tid [{telegram_id}] не привязан ни к одной конфигурации.')
        await update.message.reply_text('Ваши конфигурации не найдены. Пожалуйста, свяжитесь с администратором для добавления новых.')
        await __end_command(update)
        return
    
    for user_name in user_names:
        await __get_user_configuration(update, command, user_name)

    await __end_command(update)


async def __get_user_configuration(update: Update, command: str, user_name: str) -> None:
    requester_telegram_id = update.effective_user.id
    
    if not wireguard.check_user_exists(user_name).status:
        logger.error(f'Конфиг [{user_name}] не найден. Удаляю привязку.')
        await update.message.reply_text(f'Конфигурация [{user_name}] была удалена. Пожалуйста, свяжитесь с администратором для создания новой.')
        database.delete_user(user_name)
        return

    if wireguard.is_username_commented(user_name):
        logger.info(f'Конфиг [{user_name}] на данный момент закомментирован.')
        await update.message.reply_text(f'Конфигурация [{user_name}] на данный момент заблокирована. Пожалуйста, свяжитесь с администратором.')
        return
    
    if command == 'get_config':
        logger.info(f'Создаю и отправляю Zip-архив пользователя Wireguard [{user_name}] пользователю Tid [{requester_telegram_id}].')
        zip_ret_val = wireguard.create_zipfile(user_name)
        if zip_ret_val.status is True:
            await update.message.reply_text(f'Архив с файлом конфигурации и QR-кодом для пользователя [{user_name}]:')
            await update.message.reply_document(document=open(zip_ret_val.description, 'rb'))
            wireguard.remove_zipfile(user_name)
    
    elif command == 'get_qrcode':
        logger.info(f'Создаю и отправляю Qr-код пользователя Wireguard [{user_name}] пользователю Tid [{requester_telegram_id}].')
        png_path = wireguard.get_qrcode_path(user_name)
        if png_path.status is True:
            await update.message.reply_text(f'QR-код для пользователя [{user_name}]:')
            await update.message.reply_photo(photo=open(png_path.description, 'rb'))


# Команда /get_config
@wrappers.command_lock
async def get_config_command(update: Update, context: CallbackContext) -> None:
    telegram_id = update.effective_user.id
    if telegram_id in config.telegram_admin_ids:
        context.user_data['command'] = 'get_config'
        await update.message.reply_text((
            'Выберете, чьи файлы конфигурации вы хотите получить.\n\n'
            'Для отмены действия нажмите кнопку Закрыть.'),
            reply_markup=keyboards.CONFIG_MENU
        )
    
    else:
        await __get_configuration(update, command='get_config', telegram_id=telegram_id)


# Команда /get_qrcode
@wrappers.command_lock
async def get_qrcode_command(update: Update, context: CallbackContext) -> None:
    telegram_id = update.effective_user.id
    if telegram_id in config.telegram_admin_ids:
        context.user_data['command'] = 'get_qrcode'
        await update.message.reply_text((
            'Выберете, чьи Qr-код файлы конфигурации вы хотите получить.\n\n'
            'Для отмены действия нажмите кнопку Закрыть.'),
            reply_markup=keyboards.CONFIG_MENU
        )
    else:
        await __get_configuration(update, command='get_qrcode', telegram_id=telegram_id)


# Обработка неизвестных команд
async def unknown_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Неизвестная команда. Используйте /help для просмотра доступных команд.')


# Обработка сообщений с именами пользователей
async def handle_text(update: Update, context: CallbackContext) -> None:
    clear_command_flag = True
    try:
        command = context.user_data.get('command', None)
        if command is None:
            await update.message.reply_text('Пожалуйста, выберите команду из меню. (/menu)',
                                            reply_markup=(
                                                keyboards.ADMIN_MENU 
                                                    if update.effective_user.id in config.telegram_admin_ids
                                                        else keyboards.USER_MENU 
                                            ))
            clear_command_flag = False
            return
        
        if update.message.text.lower() == 'закрыть':
            if await __close_button_handler(update, context):
                clear_command_flag = False
                return
            
        elif update.message.text.lower() in ('свой', 'пользователя wireguard'):
            if await __get_config_buttons_handler(update, context):
                clear_command_flag = False
                return

        elif update.message.text.lower() == '/cancel':
            await cancel_command(update, context)
            clear_command_flag = False
            return


        if command == 'send_message':
            await __send_message_to_all(update, context)
            return

        need_restart_wireguard = False
        entries = update.message.text.split()
        for entry in entries:
            ret_val = None
            
            if command == 'add_user':
                ret_val = await __add_user(update, context, entry)

            elif command == 'remove_user':
                ret_val = await __rem_user(update, entry)

            elif command == 'com_uncom_user':
                ret_val = await __com_user(update, entry)
            
            elif command in ('bind_user', 'send_config'):
                ret_val = await __create_list_of_bindings(update, context, entry)

            elif command == 'unbind_user':
                await __unbind_user(update, entry)

            elif command in ('get_qrcode', 'get_config'):
                await __get_user_configuration(update, command, entry)


            if ret_val is not None:
                await update.message.reply_text(ret_val.description)
                logger.error(ret_val.description) if ret_val.status is False else logger.info(ret_val.description)

                if ret_val.status is True:
                    need_restart_wireguard = True
        
        if need_restart_wireguard:
            wireguard_utils.log_and_restart_wireguard()
            need_restart_wireguard = False

        
        if command in ('add_user', 'bind_user'):
            if len(context.user_data['wireguard_users']):
                await update.message.reply_text(
                    "Нажмите на кнопку выбора пользователя, чтобы выбрать пользователя Telegram"
                    " для связывания с переданными конфигами Wireguard.\n\n"
                    "Для отмены связывания, нажмите кнопку Закрыть.", reply_markup=keyboards.BIND_MENU)
                clear_command_flag = False
        
        elif command == 'send_config':
            if len(context.user_data['wireguard_users']):
                await update.message.reply_text(
                    "Нажмите на кнопку выбора пользователя, чтобы выбрать пользователя Telegram"
                    " , которым передать выбранные конфиги Wireguard.\n\n"
                    "Для отмены нажмите кнопку Закрыть.", reply_markup=keyboards.SEND_MENU)
                clear_command_flag = False

    except Exception as e:
        logger.error(f'Неожиданная ошибка: {e}')
        await update.message.reply_text('Произошла неожиданная ошибка. Пожалуйста, попробуйте еще раз позже.')

    finally:
        if clear_command_flag:
            # Очистка команды после выполнения
            context.user_data['command'] = None
            await __end_command(update)


async def __get_config_buttons_handler(update: Update, context: CallbackContext) -> bool:
    command = context.user_data.get('command', None)

    if command in ('get_qrcode', 'get_config'):
        if update.message.text.lower() == 'свой':
            await __get_configuration(update, command, update.effective_user.id)
            context.user_data['command'] = None
            return True

        elif update.message.text.lower() == 'пользователя wireguard':
            await update.message.reply_text((
                'Пожалуйста, введите имена пользователей Wireguard, разделяя их пробелом.\n\n'
                'Чтобы отменить ввод, используйте команду /cancel.'
            ))
            return True
    return False


async def __close_button_handler(update: Update, context: CallbackContext) -> bool:
    command = context.user_data.get('command', None)
    
    if command in ('add_user', 'bind_user'):
        await __delete_message(update, context)

        user_names = context.user_data["wireguard_users"]
        await update.message.reply_text((
                f'Связование пользователей ['
                f'{", ".join([f"<code>{user_name}</code>" for user_name in sorted(user_names)])}] отменено.'
            ),
            parse_mode='HTML'
        )

        context.user_data['command'] = None
        context.user_data['wireguard_users'] = []
        await __end_command(update)
        return True
    
    elif command in ('unbind_telegram_id', 'get_users_by_id', 'get_qrcode', 'get_config', 'send_config'):
        await __delete_message(update, context)
        await cancel_command(update, context)
        return True
    return False


async def __delete_message(update: Update, context: CallbackContext) -> None:
    # Получаем идентификатор сообщения, чтобы его удалить
    message_id = update.message.message_id
    chat_id = update.message.chat_id
    
    # Удаляем сообщение пользователя
    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)


async def __send_message_to_all(update: Update, context: CallbackContext) -> None:
    for telegram_id in database.get_all_telegram_users():
        try:
            # Отправляем сообщение каждому пользователю
            await context.bot.send_message(chat_id=telegram_id, text=update.message.text)
            logger.info(f"Сообщение успешно отправлено пользователю {telegram_id}")
        except TelegramError as e:
            logger.error(f"Не удалось отправить сообщение пользователю {telegram_id}: {e}")
            # Если не удалось отправить, удаляем пользователя из базы
            database.delete_telegram_user(telegram_id)
            logger.info(f"Пользователь {telegram_id} был удален из базы данных")


async def __validate_username(update: Update, user_name: str) -> bool:
    if not telegram_utils.validate_username(user_name):
        await update.message.reply_text(f'Неверный формат для имени пользователя'
                                        f' [{user_name}].\nИмя пользователя может содержать'
                                        f' только латинские буквы и цифры.')
        return False
    return True


async def __validate_telegram_id(update: Update, telegram_id: int) -> bool:
    if not telegram_utils.validate_telegram_id(telegram_id):
        await update.message.reply_text(
            f'Неверный формат для Telegram ID [{telegram_id}].\nTelegram ID должен быть целым числом.'
        )
        return False
    return True


async def __add_user(update: Update, context: CallbackContext, user_name: str) -> Optional[wireguard_utils.FunctionResult]:
    if not await __validate_username(update, user_name):
        return None
    # Здесь вызывается метод WireGuard для добавления пользователя
    ret_val = wireguard.add_user(user_name)

    if ret_val.status is True:
        zip_ret_val = wireguard.create_zipfile(user_name)
        if zip_ret_val.status is True:
            await update.message.reply_document(document=open(zip_ret_val.description, 'rb'))
            wireguard.remove_zipfile(user_name)
            context.user_data['wireguard_users'].append(user_name)
    return ret_val


async def __rem_user(update: Update, user_name: str) -> Optional[wireguard_utils.FunctionResult]:
    if not await __validate_username(update, user_name):
        return None
    # Здесь вызывается метод WireGuard для удаления пользователя
    ret_val = wireguard.remove_user(user_name)

    if ret_val.status is True:
        if await __check_database_state(update):
            if not database.delete_user(user_name):
                logger.error(f'Не удалось удалить информацию о пользователе [{user_name}] из базы данных.')
                await update.message.reply_text(f'Не удалось удалить информацию о пользователе'
                                                f' [{user_name}] из базы данных.')
            else:
                logger.info(f'Пользователь [{user_name}] удален из базы данных.')
    return ret_val


async def __com_user(update: Update, user_name: str) -> Optional[wireguard_utils.FunctionResult]:
    if not await __validate_username(update, user_name):
        return None
    # Здесь вызывается метод WireGuard для комментирования/раскомментирования пользователя
    return wireguard.comment_or_uncomment_user(user_name)


async def __create_list_of_bindings(update: Update, context: CallbackContext, user_name: str) -> Optional[wireguard_utils.FunctionResult]:
    if not await __validate_username(update, user_name):
        return None

    ret_val = wireguard.check_user_exists(user_name)
    if ret_val.status is True:
        ret_val = None
        context.user_data['wireguard_users'].append(user_name)
    return ret_val


async def __unbind_user(update: Update, user_name: str) -> None:
    if not await __validate_username(update, user_name):
        return

    if not await __check_database_state(update):
        return
    
    if database.user_exists(user_name):
        if database.delete_user(user_name):
            logger.info(f'Пользователь [{user_name}] успешно отвязан.')
            await update.message.reply_text(f'Пользователь [{user_name}] успешно отвязан.')
        else:
            logger.error(f'Не удалось отвязать пользователя [{user_name}].')
            await update.message.reply_text(f'Не удалось отвязать пользователя [{user_name}].')
    else:
        await update.message.reply_text(f'Пользователь [{user_name}] не привязан ни к одному Telegram ID в базе данных.')


async def handle_user_request(update: Update, context: CallbackContext) -> None:
    clear_command_flag = True
    try:
        # Удаляем сообщение о переданном пользователе
        await __delete_message(update, context)
        
        command = context.user_data.get('command', None)
        if command is None:
            await update.message.reply_text('Пожалуйста, выберите команду из меню. (/menu)',
                                reply_markup=(
                                    keyboards.ADMIN_MENU 
                                        if update.effective_user.id in config.telegram_admin_ids
                                            else keyboards.USER_MENU 
                                ))
            clear_command_flag = False
            return
        
        for shared_user in update.message.users_shared.users:
            if command in ('add_user', 'bind_user'):
                await __bind_users(update, context, shared_user)

            elif command == 'unbind_telegram_id':
                await __unbind_telegram_id(update, context, shared_user.user_id)

            elif command == 'get_users_by_id':
                await __get_bound_users_by_tid(update, context, shared_user.user_id)

            elif command in ('get_qrcode', 'get_config'):
                await __get_configuration(update, command, shared_user.user_id)
                context.user_data['command'] = None
                clear_command_flag = False

            elif command == 'send_config':
                await __send_config(update, context, shared_user)


    except Exception as e:
        logger.error(f'Неожиданная ошибка: {e}')
        await update.message.reply_text('Произошла неожиданная ошибка. Пожалуйста, попробуйте еще раз позже.')

    finally:
        if clear_command_flag:
            # Очистка команды после выполнения
            context.user_data['command'] = None
            context.user_data['wireguard_users'] = []

            await __end_command(update)


async def __bind_users(update: Update, context: CallbackContext, telegram_user: UsersShared) -> None:
    if not await __check_database_state(update):
        return
    
    telegram_id = telegram_user.user_id
    telegram_name = telegram_user.username

    for user_name in context.user_data['wireguard_users']:
        if not database.user_exists(user_name):
            if database.add_user(telegram_id, user_name):
                logger.info(f'Пользователь [{user_name}] успешно привязан к [@{telegram_name} ({telegram_id})].')
                await update.message.reply_text(f'Пользователь [{user_name}] успешно'
                                                f' привязан к [@{telegram_name} ({telegram_id})].')
            else:
                logger.error(f'Не удалось привязать пользователя [{user_name}].')
                await update.message.reply_text(f'Произошла ошибка при сохранении данных'
                                                f' [{user_name}] в базу. Операция была отменена.')
        else:
            _telegram_id = database.get_telegram_id_by_user(user_name)[0]
            _telegram_name = await telegram_utils.get_username_by_id(_telegram_id, context)
            logger.info(f'Пользователь [{user_name}] уже прикреплен к [{_telegram_name} ({_telegram_id})] в базе данных.')
            await update.message.reply_text(f'Пользователь [{user_name}] уже прикреплен к'
                                            f' [{_telegram_name} ({_telegram_id})] в базе данных.')


async def __unbind_telegram_id(update: Update, context: CallbackContext, telegram_id: int) -> None:
    if not await __validate_telegram_id(update, telegram_id):
        return

    if not await __check_database_state(update):
        return

    telegram_name = await telegram_utils.get_username_by_id(telegram_id, context)
    
    if database.telegram_id_exists(telegram_id):
        if database.delete_users_by_telegram_id(telegram_id):
            logger.info(f'Пользователи Wireguard успешно отвязаны от [{telegram_name} ({telegram_id})].')
            await update.message.reply_text(f'Пользователи Wireguard успешно отвязаны от [{telegram_name} ({telegram_id})].')
        else:
            logger.info(f'Не удалось отвязать пользователей Wireguard от [{telegram_name} ({telegram_id})].')
            await update.message.reply_text(f'Не удалось отвязать пользователей Wireguard от [{telegram_name} ({telegram_id})].')
    else:
        await update.message.reply_text(
            f'Ни один из пользователей Wireguard не прикреплен к [{telegram_name} ({telegram_id})] в базе данных.'
        )


async def __get_bound_users_by_tid(update: Update, context: CallbackContext, telegram_id: int) -> None:
    if not await __validate_telegram_id(update, telegram_id):
        return

    if not await __check_database_state(update):
        return

    telegram_name = await telegram_utils.get_username_by_id(telegram_id, context)

    if database.telegram_id_exists(telegram_id):
        user_names = database.get_users_by_telegram_id(telegram_id)
        await update.message.reply_text(
            f'Пользователи Wireguard, прикрепленные к [{telegram_name} ({telegram_id})]:'
            f' [{", ".join([f"<code>{user_name}</code>" for user_name in sorted(user_names)])}].',
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            f'Ни один из пользователей Wireguard не прикреплен к [{telegram_name} ({telegram_id})] в базе данных.'
        )


async def __send_config(update: Update, context: CallbackContext, telegram_user: UsersShared) -> None:
    if not await __check_database_state(update):
        return
    
    telegram_id = telegram_user.user_id
    telegram_name = telegram_user.username

    for user_name in context.user_data['wireguard_users']:
        if not wireguard.check_user_exists(user_name).status:
            logger.error(f'Конфиг [{user_name}] не найден.')
            await update.message.reply_text(f'Конфигурация [{user_name}] не найдена.')
            return

        if wireguard.is_username_commented(user_name):
            logger.info(f'Конфиг [{user_name}] на данный момент закомментирован.')
            await update.message.reply_text(f'Конфигурация [{user_name}] на данный момент заблокирована.')
            return
        
        logger.info(f'Создаю и отправляю Zip-архив и Qr-код пользователя Wireguard [{user_name}] пользователю [{telegram_name} ({telegram_id})].')
        zip_ret_val = wireguard.create_zipfile(user_name)
        try:
            if zip_ret_val.status is True:
                # Отправляем сообщение каждому пользователю
                await context.bot.send_message(chat_id=telegram_id, text=f'Ваш новый конфиг Wireguard.')
                await context.bot.send_document(chat_id=telegram_id, document=open(zip_ret_val.description, 'rb'))
                wireguard.remove_zipfile(user_name)

                png_path = wireguard.get_qrcode_path(user_name)
                if png_path.status is True:
                    await context.bot.send_photo(chat_id=telegram_id, photo=open(png_path.description, 'rb'))

                current_admin_id = update.effective_user.id
                current_admin_name = await telegram_utils.get_username_by_id(current_admin_id, context)

                for admin_id in config.telegram_admin_ids:
                    try:
                        if admin_id != current_admin_id:
                            text = (
                                    f'Администратор [{current_admin_name} ({current_admin_id})] отправил файлы конфигурации '
                                    f'Wireguard [{user_name}] пользователю [@{telegram_name} ({telegram_id})].'
                                )
                            await context.bot.send_message(chat_id=admin_id, text=text)
                            logger.info(text)
                    except TelegramError as e:
                        logger.error(f"Не удалось отправить сообщение администратору {admin_id}: {e}.")
                        await update.message.reply_text(f"Не удалось отправить сообщение администратору {admin_id}: {e}.")

        except TelegramError as e:
            logger.error(f"Не удалось отправить сообщение пользователю {telegram_id}: {e}.")
            await update.message.reply_text(f"Не удалось отправить сообщение пользователю {telegram_id}: {e}.")
    

async def __end_command(update: Update) -> None:
    await update.message.reply_text(
            'Команда завершина. Выбрать новую команду можно из меню (/menu).',
            reply_markup=keyboards.ADMIN_MENU if update.effective_user.id in config.telegram_admin_ids else keyboards.USER_MENU
        )


# Основная функция для запуска бота
def main() -> None:
    # Вставьте сюда свой токен, полученный у BotFather
    token = config.telegram_token
    application = ApplicationBuilder().token(token).build()

    # Базовые команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("cancel", cancel_command))

    # Команды управления пользователями Wireguard
    application.add_handler(CommandHandler("add_user", add_user_command))
    application.add_handler(CommandHandler("remove_user", remove_user_command))
    application.add_handler(CommandHandler("com_uncom_user", com_uncom_user_command))
    application.add_handler(CommandHandler("show_users_state", show_users_state_command))

    # Команды упарвления привязкой пользователей
    application.add_handler(CommandHandler("bind_user", bind_user_command))
    application.add_handler(CommandHandler("unbind_user", unbind_user_command))
    application.add_handler(CommandHandler("unbind_telegram_id", unbind_telegram_id_command))
    application.add_handler(CommandHandler("get_users_by_id", get_bound_users_by_telegram_id_command))
    application.add_handler(CommandHandler("show_all_bindings", show_all_bindings_command))

    # Команды конфигурации
    application.add_handler(CommandHandler("get_config", get_config_command))
    application.add_handler(CommandHandler("get_qrcode", get_qrcode_command))
    application.add_handler(CommandHandler("request_new_config", request_new_config_command))
    application.add_handler(CommandHandler("send_config", send_config_command))
    
    # Команды для телеграма
    application.add_handler(CommandHandler("get_telegram_id", get_telegram_id_command))
    application.add_handler(CommandHandler("get_telegram_users", get_telegram_users_command))
    application.add_handler(CommandHandler("send_message", send_message_command))

    # Обработка сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
     # Обработчик для сообщений с запросом данных пользователя
    application.add_handler(MessageHandler(filters.StatusUpdate.USER_SHARED, handle_user_request))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Запуск бота
    application.run_polling()



if __name__ == '__main__':
    try:        
        if not database.db_loaded:
            logger.error(f'Не удалось подключиться к базе данных: [{config.users_database_path}]!')
        else:
            main()
    except Exception as e:
        logger.error(f'Произошла ошибка: [{e}]')