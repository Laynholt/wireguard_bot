from .base import *
from libs.telegram import messages
from libs.wireguard import stats as wireguard_stats

from telegram import (
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup
)
from libs.wireguard.user_control import sanitize_string


class GetWireguardUserStatsCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase,
        wireguard_config_path: str,
        wireguard_log_path: str,
        return_own_stats: bool
    ) -> None:
        super().__init__(
            database
        )
    
        self.command_name = BotCommand.GET_MY_STATS if return_own_stats else BotCommand.GET_USER_STATS
        self.keyboard = Keyboard(
            title=BotCommand.GET_MY_STATS.pretty_text if return_own_stats else BotCommand.GET_USER_STATS.pretty_text,
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
                        keyboards.ButtonText.CANCEL.value.text,
                    )
                ),
                one_time_keyboard=True
            )
        )
        self.keyboard.add_parent(keyboards.WIREGUARD_STATS_KEYBOARD)
        
        self.wireguard_config_path = wireguard_config_path
        self.wireguard_log_path = wireguard_log_path
    
    
    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /get_user_stats: выводит статистику для конкретного пользователя
        телеграмм или конкретного конфига WireGuard.
        
        Команда /get_my_stats: выводит статистику по вашим конфигам WireGuard.
        """
        if self.command_name == BotCommand.GET_MY_STATS:
            if update.effective_user is None:
                if (curr_frame := inspect.currentframe()):
                    logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
                return
            
            telegram_id = update.effective_user.id
            
            if context.user_data is not None:
                context.user_data[ContextDataKeys.WIREGUARD_USERS] = []
            
            await self._create_list_of_wireguard_users_by_telegram_id(
                update, context, telegram_id
            )
            await self.__get_user_stats(update, context, own_stats=True)
            await self._end_command(update, context)

        # Иначе /get_user_stats
        else:
            if self.keyboard is None:
                return
            
            if update.message is not None:
                await update.message.reply_text(
                    text=(
                        "Выберете, чью статистику вы хотите получить.\n\n"
                        f"Для отмены нажмите кнопку {keyboards.ButtonText.CANCEL}."
                    ),
                    reply_markup=self.keyboard.reply_keyboard
                )
            if context.user_data is not None:
                context.user_data[ContextDataKeys.COMMAND] = self.command_name
                context.user_data[ContextDataKeys.WIREGUARD_USERS] = []


    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Возвращает список пользователей Wireguard, привязанных к данному Telegram.
        """
        if await self._buttons_handler(update, context):
            return
        
        if context.user_data is None or update.message is None:
            await self._end_command(update, context)
            return
    
        entries = update.message.text.split() if update.message.text is not None else []
        if entries:
            for entry in entries:
                ret_val = await self._create_list_of_wireguard_users(
                    update, context, sanitize_string(entry)
                )
            
                if ret_val is not None:
                    # Выводим сообщение с результатом (ошибка или успех)
                    await update.message.reply_text(ret_val.description)
                    if ret_val.status:
                        logger.info(ret_val.description)
                    else:
                        logger.error(ret_val.description)
            
        else:
            if update.message.users_shared is None:
                await self._end_command(update, context)
                return
            
            for shared_user in update.message.users_shared.users:
                await self._create_list_of_wireguard_users_by_telegram_id(
                    update,
                    context,
                    shared_user.user_id
                )

        await self.__get_user_stats(update, context)
        await self._end_command(update, context)


    async def __get_user_stats(self, update: Update, context: CallbackContext, own_stats: bool = False) -> None:
        """
        Выводит статистику по переданным WireGuard конфигам в context'е.
        Если конфиг недоступен или отсутствует (удалён), информация об этом
        выводится в сообщении. При необходимости лишние записи удаляются из БД.
        """
        if update.effective_user is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update effective_user is None в функции {curr_frame.f_code.co_name}')
            return
        
        if update.message is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Update message is None в функции {curr_frame.f_code.co_name}')
            return
        
        if context.user_data is None:
            if (curr_frame := inspect.currentframe()):
                logger.error(f'Context user_data is None в функции {curr_frame.f_code.co_name}')
            return
        
        telegram_id = update.effective_user.id

        if not await self._check_database_state(update):
            return

        wireguard_users = context.user_data[ContextDataKeys.WIREGUARD_USERS]
        if not wireguard_users:
            if own_stats:
                await update.message.reply_text(
                    "📁 <b>У вас нет доступных конфигураций WireGuard.</b>\n\n"
                    f"📝 <em>Используйте /{BotCommand.REQUEST_NEW_CONFIG}, чтобы отправить запрос "
                    f"администратору на создание новой конфигурации.</em>",
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    "ℹ️ <b>Статистика для заданного пользователя Telegram "
                    "или пользователей WireGuard отсутствует.</b>\n\n",
                    parse_mode="HTML"
                )
            return

        # Получаем полную статистику
        all_wireguard_stats = wireguard_stats.accumulate_wireguard_stats(
            conf_file_path=self.wireguard_config_path,
            json_file_path=self.wireguard_log_path,
            sort_by=wireguard_stats.SortBy.TRANSFER_SENT,
        )
        
        if not all_wireguard_stats:
            await update.message.reply_text("Нет данных по ни одному конфигу.")
            return

        owner_tid = self.database.get_telegram_id_by_user(wireguard_users[0])
        # Так как возвращается в базе данных нет ограничений на привязке нескольких конфигов к нескольким tid
        # (это ограничение установлено в коде нашего бота), там возвращается список.
        # Однако, если нет привязки, он может быть пустой.
        owner_tid = owner_tid[0] if owner_tid else None
        
        if owner_tid is not None and own_stats is False:
            owner_username = await telegram_utils.get_username_by_id(owner_tid, context)
            owner_part = (
                f"   👤 <b>Владелец:</b>\n"
                f"      ├ 🆔 <b>ID:</b> <code>{owner_tid}</code>\n"
                f"      └ 🔗 <b>Telegram:</b> "
                f"{'Не удалось получить' if owner_username is None else owner_username}"
            )

        else:
            owner_part = "   👤 <b>Владелец:</b>\n      └ 🚫 <i>Не назначен</i>"       

        owner_part = "" if own_stats else f"   {owner_part}\n"

        lines = []
        inactive_usernames = wireguard.get_inactive_usernames()
        
        for i, wg_user in enumerate(wireguard_users, start=1):
            user_data = all_wireguard_stats.get(wg_user, None)

            # Случай, когда статистики для пользователя нет
            # Это может быть только в том случае, если она отсутствует в логах, 
            # а также нам не удалось получить для него данные из текущего docker exec.
            
            # Причиной может быть отсутствие записи пользователя в wg0.conf, поэтому
            # лучше удалить его, раз он как-то некорректно создался, либо когда-то неправильно удалился. 
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
                if self.database.delete_user(wg_user):
                    logger.info(f"Пользователь [{wg_user}] удалён из базы данных.")
                else:
                    logger.error(
                        f"Не удалось удалить информацию о пользователе [{wg_user}] из базы данных."
                    )

                continue

            # Если всё в порядке, формируем строку со статистикой
            lines.append(
                f"\n<b>{i}]</b> <b>🌐 Конфиг:</b> <i>{wg_user}</i> "
                f"{'🔴 <b>[Неактивен]</b>' if wg_user in inactive_usernames else '🟢 <b>[Активен]</b>'}\n"
                f"{owner_part}"
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
            parse_mode="HTML",
            groups_before_delay=2,
            delay_between_groups=0.5
        )


    async def _buttons_handler(self, update: Update, context: CallbackContext) -> bool:
        if await self._cancel_button_handler(update, context):
            await self._end_command(update, context)
            return True
        
        if (
            update.message is not None
            and update.message.text == keyboards.ButtonText.WIREGUARD_USER
        ):
            if update.effective_user is not None:
                await self._delete_message(update, context)
                await update.message.reply_text(messages.ENTER_WIREGUARD_USERNAMES_MESSAGE)
            return True
        
        return False