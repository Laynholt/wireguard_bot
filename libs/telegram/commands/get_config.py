import asyncio

from curses.ascii import isdigit
from .base import *
from libs.telegram import messages

from telegram import (
    InputFile,
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup
)
from libs.wireguard.user_control import sanitize_string


class GetWireguardConfigOrQrcodeCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId],
        return_config: bool
    ) -> None:
        super().__init__(
            database
        )
    
        self.command_name = BotCommand.GET_CONFIG if return_config else BotCommand.GET_QRCODE
        self.keyboard = Keyboard(
            title=BotCommand.GET_CONFIG.pretty_text if return_config else BotCommand.GET_QRCODE.pretty_text,
            reply_keyboard=ReplyKeyboardMarkup(
                ((
                    KeyboardButton(
                        text=keyboards.ButtonText.TELEGRAM_USER.value.text,
                        request_users=KeyboardButtonRequestUsers(
                            request_id=0,
                            user_is_bot=False,
                            request_username=True,
                        )
                    ),
                    keyboards.ButtonText.WIREGUARD_USER.value.text
                    ), (
                        keyboards.ButtonText.OWN.value.text,
                        keyboards.ButtonText.CANCEL.value.text,
                    )
                ),
                one_time_keyboard=True
            )
        )
        self.keyboard.add_parent(keyboards.WIREGUARD_CONFIG_KEYBOARD)
        
        self.telegram_admin_ids= telegram_admin_ids
    
    
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
        
        if self.keyboard is None:
            return
        
        telegram_id = update.effective_user.id
        if telegram_id in self.telegram_admin_ids:
            if context.user_data is not None:
                context.user_data[ContextDataKeys.COMMAND] = self.command_name
            
            message=(
                f"Выберете, чьи {'Qr-код файлы' if self.command_name == BotCommand.GET_QRCODE else 'файлы конфигурации'}"
                " вы хотите получить.\n\n"
                f"Для отмены действия нажмите кнопку '{keyboards.ButtonText.CANCEL}'."
            )    
            
            await update.message.reply_text(
                message,
                reply_markup=self.keyboard.reply_keyboard
            )
        else:
            await self.__get_configuration(update, context, telegram_id)
            await self._end_command(update, context)


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Возвращает список пользователей Wireguard, привязанных к данному Telegram.
        """
        if await self._buttons_handler(update, context):
            return
        
        try:
            if context.user_data is None or update.message is None:
                return
        
            if update.message.users_shared is not None:
                for shared_user in update.message.users_shared.users:
                    await self.__get_configuration(
                        update, context, shared_user.user_id
                    )
            else:
                entries = update.message.text.split() if update.message.text is not None else []
                for entry in entries:
                    if entry.isdigit():
                        await self.__get_configuration(
                            update, context, int(entry)
                        )
                    else:
                        await self.__get_user_configuration(
                            update, sanitize_string(entry)
                        )
        finally:
            await self._end_command(update, context)


    async def __get_configuration(self, update: Update, context: CallbackContext, telegram_id: TelegramId) -> None:
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
            if telegram_id == update.effective_user.id:
                await update.message.reply_text(
                    "📁 <b>У вас нет доступных конфигураций WireGuard.</b>\n\n"
                    f"📝 <em>Используйте /{BotCommand.REQUEST_NEW_CONFIG}, чтобы отправить запрос "
                    f"администратору на создание новой конфигурации.</em>",
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    (
                        "ℹ️ Пользователь "
                        f"{await telegram_utils.get_username_by_id(telegram_id, context) or 'Не удалось получить имя'}"
                        f" (<code>{telegram_id}</code>) не привязан ни к одной конфигурации.\n\n"
                    ),
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
        user_exists_result = await asyncio.to_thread(wireguard.check_user_exists, user_name)
        if not user_exists_result.status:
            logger.error(f"Конфиг [{user_name}] не найден. Удаляю привязку.")
            await update.message.reply_text(
                f"🚫 Конфигурация {formatted_user} была удалена!\n\n"
                f"📝 <em>Используйте /{BotCommand.REQUEST_NEW_CONFIG}, чтобы отправить запрос "
                f"администратору на создание новой конфигурации.</em>",
                parse_mode="HTML"
            )
            self.database.delete_user(user_name)
            return

        if await asyncio.to_thread(wireguard.is_username_commented, user_name):
            logger.info(f"Конфиг [{user_name}] на данный момент закомментирован.")
            await update.message.reply_text(
                f"⚠️ Конфигурация {formatted_user} временно заблокирована!\n\n"
                f"<em>Причина: администратор ограничил доступ</em>",
                parse_mode="HTML"
            )
            return

        if self.command_name == BotCommand.GET_CONFIG:
            logger.info(
                f"Создаю и отправляю Zip-архив пользователя Wireguard [{user_name}] "
                f"пользователю Tid [{requester_telegram_id}]."
            )
            
            zip_result = await asyncio.to_thread(wireguard.create_zipfile, user_name)
            if zip_result.status:
                # Экранируем все специальные символы
                caption = (
                    f"<b>📦 Архив конфигурации</b>\n"
                    f"╔━━━━━━━━━━━━━━━━━\n"
                    f"│ <i>Содержимое:</i>\n"
                    f"│▸ 📄 Файл конфигурации\n"
                    f"│▸ 📲 QR-код для быстрого подключения\n"
                    f"╚━━━━━━━━━━━━━━━━━\n\n"
                    f"🔧 <b>Конфигурация:</b> {formatted_user}\n\n"
                    f"╔━━━━━━━━━━━━━━━━━\n"
                    f"│▸ 📂 Распакуйте архив\n"
                    f"│▸ 🛡 Откройте приложение WireGuard\n"
                    f"│▸ ➕ Нажмите «добавить туннель» (+)\n"
                    f"│▸ 📷 Отсканируйте QR-код\n"
                    f"│▸ ⚙️ Или импортируйте .conf файл\n"
                    f"╚━━━━━━━━━━━━━━━━━"
                )
                
                with open(zip_result.description, "rb") as zip_file:
                    await update.message.reply_document(
                        document=zip_file,
                        filename=f"{user_name}.zip",
                        caption=caption,
                        parse_mode="HTML"
                    )
                await asyncio.to_thread(wireguard.remove_temp_artifact, zip_result.description)
            else:
                logger.error(f'Не удалось создать архив для {user_name}. Ошибка: [{zip_result.description}]')
                await update.message.reply_text(
                    f"❌ Не удалось создать архив для {formatted_user}!\n"
                    f"<em>Ошибка: {zip_result.description}</em>",
                    parse_mode="HTML"
                )

        elif self.command_name == BotCommand.GET_QRCODE:
            logger.info(
                f"Создаю и отправляю Qr-код пользователя Wireguard [{user_name}] "
                f"пользователю Tid [{requester_telegram_id}]."
            )
            
            png_path = await asyncio.to_thread(wireguard.get_qrcode_path, user_name)
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
                
                try:
                    with open(png_path.description, "rb") as png_file:
                        await update.message.reply_photo(
                            photo=InputFile(png_file, filename=f"{user_name}.png"),
                            caption=caption,
                            parse_mode="HTML"
                        )
                finally:
                    await asyncio.to_thread(wireguard.remove_temp_artifact, png_path.description)
            else:
                logger.error(f'Не удалось создать архив для {user_name}. Ошибка: [{png_path.description}]')
                await update.message.reply_text(
                    f"❌ Не удалось сгенерировать QR-код для {formatted_user}\n"
                    f"<em>Ошибка: {png_path.description}</em>",
                    parse_mode="HTML"
                )


    async def _buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        if await self._cancel_button_handler(update, context):
            await self._end_command(update, context)
            return True
        
        if (
            update.message is not None
            and update.message.text in (
                keyboards.ButtonText.OWN,
                keyboards.ButtonText.WIREGUARD_USER
            )
        ):
            await self._delete_message(update, context)
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

        if update.message.text == keyboards.ButtonText.OWN and update.effective_user is not None:
            await self.__get_configuration(update, context, update.effective_user.id)
            await self._end_command(update, context)
            return True

        elif update.message.text == keyboards.ButtonText.WIREGUARD_USER.value.text:
            await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
            return True
        return False
