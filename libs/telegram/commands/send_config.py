import asyncio

from .base import *
from libs.telegram import messages

from telegram import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButtonRequestUsers
)
from libs.wireguard.user_control import sanitize_string


class SendConfigCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId]
    ) -> None:
        super().__init__(
            database
        )
    
        self.command_name = BotCommand.SEND_CONFIG
        self.keyboard = Keyboard(
            title=BotCommand.SEND_CONFIG.pretty_text,
            reply_keyboard=ReplyKeyboardMarkup(
                (
                    (
                        KeyboardButton(
                            text=keyboards.ButtonText.SELECT_TELEGRAM_USER.value.text,
                            request_users=KeyboardButtonRequestUsers(
                                request_id=0,
                                user_is_bot=False,
                                request_username=True,
                            )
                        ),
                        keyboards.ButtonText.CANCEL.value.text
                    ),
                ),
                one_time_keyboard=True
            )
        )
        self.keyboard.add_parent(keyboards.WIREGUARD_CONFIG_KEYBOARD)
        
        self.telegram_admin_ids = telegram_admin_ids
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /send_config: администратор отправляет конкретные конфиги Wireguard выбранным пользователям.
        """
        if update.message is not None:
            await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
        if context.user_data is not None:
            context.user_data[ContextDataKeys.COMMAND] = self.command_name
            context.user_data[ContextDataKeys.WIREGUARD_USERS] = []


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Отправляет конфиги пользователя(-ей) Wireguard пользователю Telegram.
        """
        need_clean_up = True
        try:
            if await self._buttons_handler(update, context):
                return
            
            if context.user_data is None or update.message is None or self.keyboard is None:
                return
            
            if update.message.users_shared is not None:
                for shared_user in update.message.users_shared.users:
                    await self.__send_config(update, context, shared_user.user_id)
            else:    
                entries = update.message.text.split() if update.message.text is not None else []
                for entry in entries:
                    await self._create_list_of_wireguard_users(
                        update, context, sanitize_string(entry)
                    )
                    
                if len(context.user_data[ContextDataKeys.WIREGUARD_USERS]) > 0:                    
                    await update.message.reply_text(
                        (
                            f"Выберете пользователя телеграм через кнопку "
                            f"'{keyboards.ButtonText.SELECT_TELEGRAM_USER}'.\n\n"
                            f"Чтобы отменить команду, нажмите {keyboards.ButtonText.CANCEL}."
                        ),
                        reply_markup=self.keyboard.reply_keyboard
                    )
                    need_clean_up = False
        finally:
            if need_clean_up:
                await self._end_command(update, context)
        

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
        if not await self._check_database_state(update):
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

        for user_name in context.user_data[ContextDataKeys.WIREGUARD_USERS]:
            check_result = await asyncio.to_thread(wireguard.check_user_exists, user_name)
            if not check_result.status:
                logger.error(f"Конфиг [{user_name}] не найден.")
                await update.message.reply_text(f"Конфигурация [{user_name}] не найдена.")
                return

            if await asyncio.to_thread(wireguard.is_username_commented, user_name):
                logger.info(f"Конфиг [{user_name}] на данный момент закомментирован.")
                await update.message.reply_text(
                    f"Конфигурация [{user_name}] на данный момент заблокирована."
                )
                return

            logger.info(
                f"Создаю и отправляю Zip-архив и Qr-код пользователя Wireguard [{user_name}] "
                f"пользователю [{telegram_username} ({telegram_id})]."
            )
            zip_result = await asyncio.to_thread(wireguard.create_zipfile, user_name)
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
                    
                    with open(zip_result.description, "rb") as zip_file:
                        await context.bot.send_document(
                            chat_id=telegram_id,
                            document=zip_file,
                            caption=caption,
                            parse_mode="HTML"
                        )

                    await asyncio.to_thread(wireguard.remove_zipfile, user_name)

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


    async def _buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        if await self._cancel_button_handler(update, context):
            return True
        return False
