from .base import *
from libs.telegram import messages

from telegram import (
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup
)


class GetWireguardConfigOrQrcodeCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId],
        return_config: bool
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids,
        )
    
        self.command_name = BotCommands.GET_CONFIG if return_config else BotCommands.GET_QRCODE
        self.keyboard = ((
                KeyboardButton(
                    text=keyboards.BUTTON_TELEGRAM_USER.text,
                    request_users=KeyboardButtonRequestUsers(
                        request_id=0,
                        user_is_bot=False,
                        request_username=True,
                    )
                ),
                keyboards.BUTTON_WIREGUARD_USER.text
            ), (
                keyboards.BUTTON_OWN.text,
                keyboards.BUTTON_CLOSE.text,
            )
        )
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /get_config: выдаёт пользователю .zip конфигурации Wireguard.
        Команда /get_qrcode: выдаёт пользователю QR-код конфигурации Wireguard.
        Если пользователь администратор — позволяет выбрать, чьи конфиги получать.
        """
        if update.effective_user is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
            return

        if update.message is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
            return
        
        telegram_id = update.effective_user.id
        if telegram_id in self.telegram_admin_ids:
            if context.user_data is not None:
                context.user_data["command"] = self.command_name
            
            message=(
                f"Выберете, чьи {'Qr-код файлы' if self.command_name == BotCommands.GET_QRCODE else 'файлы конфигурации'}"
                " вы хотите получить.\n\n"
                f"Для отмены действия нажмите кнопку '{keyboards.BUTTON_CLOSE}'."
            )    
            
            await update.message.reply_text(
                message,
                reply_markup=ReplyKeyboardMarkup(keyboard=self.keyboard, one_time_keyboard=True)
            )
        else:
            await self.__get_configuration(update, telegram_id)
            await self.__end_command(update, context)


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Возвращает список пользователей Wireguard, привязанных к данному Telegram.
        """
        if await self.__buttons_handler(update, context):
            return
        
        if context.user_data is None or update.message is None:
            await self.__end_command(update, context)
            return
    
        entries = update.message.text.split() if update.message.text is not None else []
        if entries:
            for entry in entries:
                await self.__get_user_configuration(update, entry)
        
        else:
            if update.message.users_shared is None:
                await self.__end_command(update, context)
                return
            
            for shared_user in update.message.users_shared.users:
                await self.__get_configuration(
                    update, shared_user.user_id
                )

        await self.__end_command(update, context)


    async def __get_configuration(self, update: Update, telegram_id: TelegramId) -> None:
        """
        Универсальная функция получения и отправки пользователю конфигурационных файлов/QR-кода.
        """
        if update.effective_user is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
            return
        
        if update.message is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
            return
        
        if not self.database.db_loaded:
            logger.error("Ошибка! База данных не загружена!")
            await update.message.reply_text(
                "🛑 <b>Ошибка базы данных</b>. Не удалось получить данные.\n"
                "📞 Свяжитесь с администратором.",
                parse_mode="HTML"
            )
            return

        user_names = self.database.get_users_by_telegram_id(telegram_id)
        if not user_names:
            logger.info(f"Пользователь Tid [{telegram_id}] не привязан ни к одной конфигурации.")
            await update.message.reply_text(
                "📁 <b>У вас нет доступных конфигураций WireGuard.</b>\n\n"
                f"📝 <em>Используйте /{BotCommands.REQUEST_NEW_CONFIG}, чтобы отправить запрос "
                f"администратору на создание новой конфигурации.</em>",
                parse_mode="HTML"
            )
            return

        for user_name in user_names:
            await self.__get_user_configuration(update, user_name)


    async def __get_user_configuration(self, update: Update, user_name: str) -> None:
        """
        Отправляет пользователю .zip-конфиг или QR-код в зависимости от команды.
        Если пользователь заблокирован или конфиг отсутствует, выводится соответствующее сообщение.
        """
        if update.effective_user is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
            return
        
        if update.message is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
            return
        
        requester_telegram_id = update.effective_user.id

        # Форматируем имя конфига для сообщений
        formatted_user = f"🔐 <em>{user_name}</em>"

        # Проверка существования конфига
        user_exists_result = wireguard.check_user_exists(user_name)
        if not user_exists_result.status:
            logger.error(f"Конфиг [{user_name}] не найден. Удаляю привязку.")
            await update.message.reply_text(
                f"🚫 Конфигурация {formatted_user} была удалена!\n\n"
                f"📝 <em>Используйте /{BotCommands.REQUEST_NEW_CONFIG}, чтобы отправить запрос "
                f"администратору на создание новой конфигурации.</em>",
                parse_mode="HTML"
            )
            self.database.delete_user(user_name)
            return

        if wireguard.is_username_commented(user_name):
            logger.info(f"Конфиг [{user_name}] на данный момент закомментирован.")
            await update.message.reply_text(
                f"⚠️ Конфигурация {formatted_user} временно заблокирована!\n\n"
                f"<em>Причина: администратор ограничил доступ</em>",
                parse_mode="HTML"
            )
            return

        if self.command_name == BotCommands.GET_CONFIG:
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
                    f"❌ Не удалось создать архив для {formatted_user}!\n"
                    f"<em>Ошибка: {zip_result.description}</em>",
                    parse_mode="HTML"
                )

        elif self.command_name == BotCommands.GET_QRCODE:
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


    async def __buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        if await self.__close_button_handler(update, context):
            await self.__end_command(update, context)
            return True
        
        if (
            update.message is not None
            and update.message.text in (
                keyboards.BUTTON_OWN,
                keyboards.BUTTON_WIREGUARD_USER
            )
        ):
            if update.effective_user is not None:
                await self.__delete_message(update, context)
                await self.__get_config_buttons_handler(update, context)
            return True
        
        return False


    async def __get_config_buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        """
        Обработка нажатия кнопок (Own Config или Wg User Config) для команд get_qrcode / get_config.
        Возвращает True, если нужно прервать дальнейший парсинг handle_text.
        """
        if context.user_data is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Context user_data is None в функции {curr_frame.f_code.co_name}')
            return False
            
        if update.message is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
            return False

        if update.message.text == keyboards.BUTTON_OWN and update.effective_user is not None:
            await self.__get_configuration(update, update.effective_user.id)
            await self.__end_command(update, context)
            return True

        elif update.message.text == keyboards.BUTTON_WIREGUARD_USER.text:
            await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
            return True
        return False