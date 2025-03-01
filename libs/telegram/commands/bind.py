from .base import *
from libs.telegram import messages

from telegram import (
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup
)

from typing import Final


BIND_KEYBOARD: Final = ((
        KeyboardButton(
            text=keyboards.BUTTON_BIND_WITH_TG_USER.text,
            request_users=KeyboardButtonRequestUsers(
                request_id=0,
                user_is_bot=False,
                request_username=True,
            )
        ),
        keyboards.BUTTON_BIND_TO_YOURSELF.text
    ), (
        keyboards.BUTTON_CLOSE.text,
    )
)

class BindWireguardUserCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId]
    ) -> None:
        super().__init__(
            database,
            telegram_admin_ids,
        )
    
        self.command_name = BotCommands.BIND_USER
        self.keyboard = BIND_KEYBOARD
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /bind_user: привязывает существующие конфиги Wireguard к Telegram-пользователю.
        """
        if update.message is not None:
            await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
        if context.user_data is not None:
            context.user_data["command"] = self.command_name
            context.user_data["wireguard_users"] = []


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Привязывает пользователя(-ей) Wireguard к Telegram Id.
        """
        if await self._buttons_handler(update, context):
            await self._end_command(update, context)
            return
        
        if context.user_data is None or update.message is None:
            await self._end_command(update, context)
            return
        
        # Если пользователь вызвал команду сам, а не через add_user
        if len(context.user_data["wireguard_users"]) > 0:
            
            entries = update.message.text.split() if update.message.text is not None else []
            for entry in entries:
                ret_val = await self._create_list_of_wireguard_users(update, context, entry)
                
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
                        f"Нажмите на кнопку '{keyboards.BUTTON_BIND_WITH_TG_USER}', "
                        "чтобы выбрать пользователя Telegram для связывания с переданными конфигами Wireguard.\n\n"
                        f"Для отмены связывания, нажмите кнопку '{keyboards.BUTTON_CLOSE}'."
                    ),
                    reply_markup=ReplyKeyboardMarkup(self.keyboard),
                )
        
        else:
            try:
                if update.message.users_shared is None:
                    return
                
                for shared_user in update.message.users_shared.users:
                    await self.__bind_users(update, context, shared_user.user_id)
            
            finally:
                await self._end_command(update, context)


    async def __bind_users(
        self,
        update: Update,
        context: CallbackContext,
        telegram_id: TelegramId
    ) -> None:
        """
        Привязывает список Wireguard-конфигов из context.user_data['wireguard_users']
        к выбранному Telegram ID (tid).
        """
        if not await self._check_database_state(update):
            return

        if context.user_data is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Context user_data is None в функции {curr_frame.f_code.co_name}')
            return

        telegram_username = await telegram_utils.get_username_by_id(telegram_id, context)

        for user_name in context.user_data["wireguard_users"]:
            if not self.database.is_user_exists(user_name):
                # user_name ещё не привязан к никому
                if self.database.add_user(telegram_id, user_name):
                    logger.info(
                        f"Пользователь [{user_name}] успешно привязан к [{telegram_username} ({telegram_id})]."
                    )
                    if update.message is not None:
                        await update.message.reply_text(
                            f"Пользователь [{user_name}] успешно "
                            f"привязан к [{telegram_username} ({telegram_id})]."
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
                already_tid = self.database.get_telegram_id_by_user(user_name)[0]
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


    async def _buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        if await self._close_button_handler(update, context):
            return True
        
        if update.message is not None and update.message.text == keyboards.BUTTON_BIND_TO_YOURSELF:
            if update.effective_user is not None:
                await self._delete_message(update, context)
                await self.__bind_users(update, context, update.effective_user.id)
            return True
        
        return False


    async def _close_button_handler(self, update: Update, context: CallbackContext) -> bool:
        """
        Обработка кнопки Закрыть (BUTTON_CLOSE).
        Возвращает True, если нужно прервать дальнейший парсинг handle_text.
        """
        if not context.user_data:
            return False
        
        if update.message is None or update.message.text != keyboards.BUTTON_CLOSE:
            return False
        
        current_command = context.user_data.get("command", None)

        if current_command == self.command_name:
            await self._delete_message(update, context)
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
        return False