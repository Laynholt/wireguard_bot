from .base import *
from libs.telegram import messages

from telegram import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButtonRequestUsers
)


class SendConfigCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId]
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids,
        )
    
        self.command_name = BotCommands.SEND_CONFIG
        self.keyboard = ((
                KeyboardButton(
                    text=keyboards.BUTTON_SELECT_TELEGRAM_USER.text,
                    request_users=KeyboardButtonRequestUsers(
                        request_id=0,
                        user_is_bot=False,
                        request_username=True,
                    )
                ),
                keyboards.BUTTON_CLOSE.text
            ),
        )
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /send_config: администратор отправляет конкретные конфиги Wireguard выбранным пользователям.
        """
        if update.message is not None:
            await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
        if context.user_data is not None:
            context.user_data["command"] = self.command_name
            context.user_data["wireguard_users"] = []


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Отправляет конфиги пользователя(-ей) Wireguard пользователю Telegram.
        """
        if await self.__buttons_handler(update, context):
            await self.__end_command(update, context)
            return
        
        if context.user_data is None or update.message is None:
            await self.__end_command(update, context)
            return
        
        # Если пользователь вызвал команду сам, а не через add_user
        if len(context.user_data["wireguard_users"]) > 0:
            
            entries = update.message.text.split() if update.message.text is not None else []
            for entry in entries:
                ret_val = await self.__create_list_of_wireguard_users(
                    update, context, entry
                )
                
                if ret_val is not None:
                    # Выводим сообщение с результатом (ошибка или успех)
                    await update.message.reply_text(ret_val.description)
                    if ret_val.status:
                        logger.info(ret_val.description)
                    else:
                        logger.error(ret_val.description)
            
            if len(context.user_data["wireguard_users"]) > 0:
                await update.message.reply_text(
                    (
                        f"Выберете пользователя телеграм через кнопку "
                        f"'{keyboards.BUTTON_SELECT_TELEGRAM_USER}'.\n\n"
                        f"Чтобы отменить команду, нажмите {keyboards.BUTTON_CLOSE}."
                    ),
                    reply_markup=ReplyKeyboardMarkup(self.keyboard, one_time_keyboard=True),
                )
        
        else:
            if update.message.users_shared is None:
                await self.__end_command(update, context)
                return
            
            for shared_user in update.message.users_shared.users:
                await self.__send_config(update, context, shared_user.user_id)
            
            await self.__end_command(update, context)


    async def __send_config(
        self, 
        update: Update,
        context: CallbackContext,
        telegram_id: TelegramId
    ) -> None:
        """
        Администратор отправляет пользователю (telegram_user) zip-файлы и QR-коды
        для списка конфигов из context.user_data['wireguard_users'].
        """
        if not await self.__check_database_state(update):
            return
        
        if update.message is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
            return
        
        if context.user_data is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Context user_data is None в функции {curr_frame.f_code.co_name}')
            return

        telegram_username = await telegram_utils.get_username_by_id(
            telegram_id,
            context
        ) or "NoUsername"

        for user_name in context.user_data["wireguard_users"]:
            check_result = wireguard.check_user_exists(user_name)
            if not check_result.status:
                logger.error(f"Конфиг [{user_name}] не найден.")
                await update.message.reply_text(f"Конфигурация [{user_name}] не найдена.")
                return

            if wireguard.is_username_commented(user_name):
                logger.info(f"Конфиг [{user_name}] на данный момент закомментирован.")
                await update.message.reply_text(
                    f"Конфигурация [{user_name}] на данный момент заблокирована."
                )
                return

            logger.info(
                f"Создаю и отправляю Zip-архив и Qr-код пользователя Wireguard [{user_name}] "
                f"пользователю [{telegram_username} ({telegram_id})]."
            )
            zip_result = wireguard.create_zipfile(user_name)
            try:
                if zip_result.status:
                    formatted_user = f"🔐 <em>{user_name}</em>"
                    caption = (
                        f"<b>📦 Новый архив конфигурации</b>\n"
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
                    
                    await context.bot.send_document(
                        chat_id=telegram_id,
                        document=open(zip_result.description, "rb"),
                        caption=caption,
                        parse_mode="HTML"
                    )

                    wireguard.remove_zipfile(user_name)

                    # png_path = wireguard.get_qrcode_path(user_name)
                    # if png_path.status:
                    #     await context.bot.send_photo(chat_id=tid, photo=open(png_path.description, "rb"))

                    current_admin_id = -1
                    current_admin_name = "NoUsername"
                    
                    if update.effective_user is not None:
                        current_admin_id = update.effective_user.id
                        current_admin_name = await telegram_utils.get_username_by_id(
                            current_admin_id, context
                        )

                    # Оповещаем админов о действии
                    text = (
                        f"Администратор [{current_admin_name} ({current_admin_id})] отправил "
                        f"файлы конфигурации Wireguard [{user_name}] пользователю "
                        f"[{telegram_username} ({telegram_id})]."
                    )
                    pretty_text = (
                        f"👤 <b>Администратор:</b> {current_admin_name} (<code>{current_admin_id}</code>)\n"
                        f"📤 <b>Отправил конфигурацию WireGuard</b>\n"
                        f"👤 <b>Пользователь:</b> {telegram_username} (<code>{telegram_id}</code>)"
                    )
                    for admin_id in self.telegram_admin_ids:
                        if admin_id == current_admin_id:
                            await update.message.reply_text((
                                f"Конфигурация [{user_name}] успешно отправлена"
                                f" пользователю [{telegram_username} ({telegram_id})]."
                            ))
                            continue
                        try:
                            await context.bot.send_message(chat_id=admin_id, text=pretty_text, parse_mode="HTML")
                            logger.info(f"Сообщение для [{admin_id}]: {text}")
                        except TelegramError as e:
                            logger.error(f"Не удалось отправить сообщение администратору {admin_id}: {e}.")
                            await update.message.reply_text(
                                f"Не удалось отправить сообщение администратору {admin_id}: {e}."
                            )

            except TelegramError as e:
                logger.error(f"Не удалось отправить сообщение пользователю {telegram_id}: {e}.")
                await update.message.reply_text(f"Не удалось отправить сообщение пользователю {telegram_id}: {e}.")


    async def __buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        if await self.__close_button_handler(update, context):
            return True
        return False