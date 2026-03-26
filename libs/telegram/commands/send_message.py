from __future__ import annotations

import os
import re
import tempfile

from asyncio import Semaphore
from dataclasses import dataclass

from .base import *


class SendMessageCommand(BaseCommand):
    _CTX_PREFIX = ContextDataKeys.SEND_MESSAGE_PREFIX.value
    CTX_STAGE = f"{_CTX_PREFIX}stage"
    CTX_RECIPIENT_IDS = f"{_CTX_PREFIX}recipient_ids"
    CTX_RECIPIENT_LABELS = f"{_CTX_PREFIX}recipient_labels"
    CTX_TARGET_IDS = f"{_CTX_PREFIX}target_ids"

    RANGE_TOKEN_PATTERN = re.compile(r"^(?P<start>\d+)-(?P<end>\d+)$")

    @dataclass(frozen=True)
    class Recipient:
        telegram_id: TelegramId
        label: str

    @dataclass(frozen=True)
    class BroadcastPayload:
        kind: str
        text: Optional[str] = None
        file_path: Optional[str] = None
        filename: Optional[str] = None
        duration: Optional[int] = None
        performer: Optional[str] = None
        title: Optional[str] = None

    def __init__(
        self,
        database: UserDatabase,
        telegram_admin_ids: Iterable[TelegramId],
        telegram_user_ids_cache: set[TelegramId],
        semaphore: Semaphore,
    ) -> None:
        super().__init__(database)
        self.command_name = BotCommand.SEND_MESSAGE
        self.telegram_admin_ids = set(telegram_admin_ids)
        self.telegram_user_ids_cache = telegram_user_ids_cache
        self.semaphore = semaphore

    async def request_input(self, update: Update, context: CallbackContext):
        """
        Команда /send_message: запускает рассылку по выбранным Telegram-пользователям.
        """
        if update.message is None or context.user_data is None:
            return

        recipients = await self.__build_recipients(context)
        if not recipients:
            await update.message.reply_text(
                "Нет доступных Telegram-пользователей для рассылки."
            )
            return

        context.user_data[ContextDataKeys.COMMAND] = self.command_name
        context.user_data[self.CTX_STAGE] = "await_targets"
        context.user_data[self.CTX_RECIPIENT_IDS] = [recipient.telegram_id for recipient in recipients]
        context.user_data[self.CTX_RECIPIENT_LABELS] = {
            recipient.telegram_id: recipient.label for recipient in recipients
        }
        context.user_data.pop(self.CTX_TARGET_IDS, None)

        await self.__prompt_recipient_selection(update, recipients)

    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        """
        Обрабатывает выбор получателей и содержимое рассылки.
        """
        if update.message is None or context.user_data is None:
            await self._end_command(update, context)
            return None

        stage = context.user_data.get(self.CTX_STAGE)
        if stage == "await_targets":
            await self.__handle_target_selection(update, context)
            return None

        if stage == "await_content":
            await self.__handle_content(update, context)
            return None

        await update.message.reply_text(
            "Состояние рассылки потеряно. Запустите команду заново."
        )
        self.__reset_state(context)
        await self._end_command(update, context)
        return None

    async def __build_recipients(
        self,
        context: CallbackContext,
    ) -> list[Recipient]:
        usernames = await telegram_utils.get_usernames_in_bulk(
            self.telegram_user_ids_cache,
            context,
            self.semaphore,
        )

        recipients = [
            self.Recipient(
                telegram_id=telegram_id,
                label=f"{usernames.get(telegram_id) or 'Без username'} (<code>{telegram_id}</code>)",
            )
            for telegram_id in self.telegram_user_ids_cache
        ]
        recipients.sort(key=lambda recipient: (recipient.label.lower(), recipient.telegram_id))
        return recipients

    async def __prompt_recipient_selection(
        self,
        update: Update,
        recipients: list[Recipient],
    ) -> None:
        if update.message is None:
            return

        await update.message.reply_text(
            (
                "<b>Выберите получателей рассылки</b>\n\n"
                "Введите:\n"
                "• <code>*</code> или <code>-1</code> для всех пользователей\n"
                "• номера через пробел или запятую: <code>1 2 5</code>, <code>1,2,5</code>\n"
                "• диапазоны через тире: <code>1-5</code>\n"
                "• смешанный вариант: <code>1, 3-5 9</code>\n\n"
                "Список пользователей:"
            ),
            parse_mode="HTML",
        )

        lines = [
            f"{index}. {recipient.label}"
            for index, recipient in enumerate(recipients, start=1)
        ]
        batched_lines = telegram_utils.build_batched_lines(
            lines,
            max_items_per_batch=25,
        )
        await telegram_utils.send_batched_messages(
            update,
            batched_lines,
            parse_mode="HTML",
        )
        await update.message.reply_text(
            f"Чтобы отменить рассылку, используйте /{BotCommand.CANCEL}."
        )

    async def __handle_target_selection(
        self,
        update: Update,
        context: CallbackContext,
    ) -> None:
        if update.message is None or context.user_data is None:
            return

        if update.message.text is None:
            await update.message.reply_text(
                "Введите номера пользователей текстом. Например: 1, 2-4 или *."
            )
            return

        recipient_ids: list[TelegramId] = context.user_data.get(self.CTX_RECIPIENT_IDS, [])
        parsed_indexes, error_text = self.__parse_selection(
            update.message.text,
            len(recipient_ids),
        )
        if error_text is not None:
            await update.message.reply_text(f"{error_text}\nПовторите ввод.")
            return

        target_ids = [recipient_ids[index - 1] for index in parsed_indexes]
        context.user_data[self.CTX_TARGET_IDS] = target_ids
        context.user_data[self.CTX_STAGE] = "await_content"

        await update.message.reply_text(
            f"Получатели выбраны: {len(target_ids)}."
        )
        await self.__send_selected_recipients(update, context, target_ids)
        await update.message.reply_text(
            (
                "Теперь отправьте текст сообщения, изображение, видео, аудио или файл.\n"
                "Для вложений можно добавить подпись.\n\n"
                f"Чтобы отменить рассылку, используйте /{BotCommand.CANCEL}."
            )
        )

    def __parse_selection(
        self,
        raw_text: str,
        recipients_count: int,
    ) -> tuple[list[int], Optional[str]]:
        normalized = re.sub(r"(?<=\d)\s*-\s*(?=\d)", "-", raw_text.strip())
        tokens = [token for token in re.split(r"[\s,]+", normalized) if token]

        if not tokens:
            return [], "Не удалось распознать ни одного элемента выбора."

        if "*" in tokens or "-1" in tokens:
            return list(range(1, recipients_count + 1)), None

        selected_indexes: set[int] = set()
        for token in tokens:
            if token.isdigit():
                index = int(token)
                if not 1 <= index <= recipients_count:
                    return [], f"Номер {index} выходит за пределы списка."
                selected_indexes.add(index)
                continue

            range_match = self.RANGE_TOKEN_PATTERN.fullmatch(token)
            if range_match is None:
                return [], f"Неверный формат элемента [{token}]."

            start = int(range_match.group("start"))
            end = int(range_match.group("end"))
            if start > end:
                return [], f"Диапазон [{token}] должен быть возрастающим."
            if start < 1 or end > recipients_count:
                return [], f"Диапазон [{token}] выходит за пределы списка."

            selected_indexes.update(range(start, end + 1))

        return sorted(selected_indexes), None

    async def __send_selected_recipients(
        self,
        update: Update,
        context: CallbackContext,
        target_ids: list[TelegramId],
    ) -> None:
        if update.message is None or context.user_data is None:
            return

        recipient_labels: dict[TelegramId, str] = context.user_data.get(self.CTX_RECIPIENT_LABELS, {})
        lines = [
            recipient_labels.get(telegram_id, f"<code>{telegram_id}</code>")
            for telegram_id in target_ids
        ]
        batched_lines = telegram_utils.build_batched_lines(
            lines,
            max_items_per_batch=20,
        )
        await update.message.reply_text(
            "<b>Сообщение будет отправлено этим пользователям:</b>",
            parse_mode="HTML",
        )
        await telegram_utils.send_batched_messages(
            update,
            batched_lines,
            parse_mode="HTML",
        )

    async def __handle_content(
        self,
        update: Update,
        context: CallbackContext,
    ) -> None:
        if update.message is None or context.user_data is None:
            return

        target_ids: list[TelegramId] = context.user_data.get(self.CTX_TARGET_IDS, [])
        if not target_ids:
            await update.message.reply_text(
                "Не найдены получатели рассылки. Запустите команду заново."
            )
            self.__reset_state(context)
            await self._end_command(update, context)
            return

        try:
            payload = await self.__extract_payload(update, context)
        except ValueError as error:
            await update.message.reply_text(str(error))
            return

        try:
            failed_ids = await self.__broadcast_payload(
                context=context,
                payload=payload,
                target_ids=target_ids,
            )
        finally:
            if payload.file_path is not None:
                self.__remove_temp_file(payload.file_path)

        await self.__report_broadcast_result(update, context, target_ids, failed_ids)
        self.__reset_state(context)
        await self._end_command(update, context)

    async def __extract_payload(
        self,
        update: Update,
        context: CallbackContext,
    ) -> BroadcastPayload:
        if update.message is None:
            raise ValueError("Не удалось получить сообщение для рассылки.")

        if update.message.photo:
            caption = (update.message.caption or "").strip() or None
            if caption is not None and len(caption) > 1024:
                raise ValueError("Подпись к изображению слишком длинная. Максимум 1024 символа.")

            photo = update.message.photo[-1]
            telegram_file = await context.bot.get_file(photo.file_id)
            file_path = await self.__download_temp_file(
                telegram_file=telegram_file,
                fallback_suffix=".jpg",
            )
            return self.BroadcastPayload(kind="photo", text=caption, file_path=file_path)

        if update.message.video is not None:
            caption = (update.message.caption or "").strip() or None
            if caption is not None and len(caption) > 1024:
                raise ValueError("Подпись к видео слишком длинная. Максимум 1024 символа.")

            telegram_file = await context.bot.get_file(update.message.video.file_id)
            suffix = os.path.splitext(update.message.video.file_name or "")[1] or ".mp4"
            file_path = await self.__download_temp_file(
                telegram_file=telegram_file,
                fallback_suffix=suffix,
            )
            return self.BroadcastPayload(
                kind="video",
                text=caption,
                file_path=file_path,
                filename=update.message.video.file_name,
                duration=update.message.video.duration,
            )

        if update.message.audio is not None:
            caption = (update.message.caption or "").strip() or None
            if caption is not None and len(caption) > 1024:
                raise ValueError("Подпись к аудио слишком длинная. Максимум 1024 символа.")

            telegram_file = await context.bot.get_file(update.message.audio.file_id)
            suffix = os.path.splitext(update.message.audio.file_name or "")[1] or ".mp3"
            file_path = await self.__download_temp_file(
                telegram_file=telegram_file,
                fallback_suffix=suffix,
            )
            return self.BroadcastPayload(
                kind="audio",
                text=caption,
                file_path=file_path,
                filename=update.message.audio.file_name,
                duration=update.message.audio.duration,
                performer=update.message.audio.performer,
                title=update.message.audio.title,
            )

        if update.message.document is not None:
            caption = (update.message.caption or "").strip() or None
            if caption is not None and len(caption) > 1024:
                raise ValueError("Подпись к файлу слишком длинная. Максимум 1024 символа.")

            telegram_file = await context.bot.get_file(update.message.document.file_id)
            suffix = os.path.splitext(update.message.document.file_name or "")[1] or ".bin"
            file_path = await self.__download_temp_file(
                telegram_file=telegram_file,
                fallback_suffix=suffix,
            )
            return self.BroadcastPayload(
                kind="document",
                text=caption,
                file_path=file_path,
                filename=update.message.document.file_name,
            )

        if update.message.text is not None and update.message.text.strip():
            return self.BroadcastPayload(kind="text", text=update.message.text)

        raise ValueError(
            "Поддерживаются только текст, изображение и файл. Отправьте сообщение заново."
        )

    async def __download_temp_file(
        self,
        telegram_file,
        fallback_suffix: str,
    ) -> str:
        suffix = os.path.splitext(telegram_file.file_path or "")[1] or fallback_suffix
        fd, temp_path = tempfile.mkstemp(prefix="telegram_broadcast_", suffix=suffix)
        os.close(fd)
        await telegram_file.download_to_drive(custom_path=temp_path)
        return temp_path

    async def __broadcast_payload(
        self,
        context: CallbackContext,
        payload: BroadcastPayload,
        target_ids: list[TelegramId],
    ) -> list[TelegramId]:
        failed_ids: list[TelegramId] = []

        for telegram_id in target_ids:
            keyboard = (
                keyboards.KEYBOARD_MANAGER.get_admin_main_keyboard()
                if telegram_id in self.telegram_admin_ids
                else keyboards.KEYBOARD_MANAGER.get_user_main_keyboard()
            )
            try:
                if payload.kind == "text":
                    await context.bot.send_message(
                        chat_id=telegram_id,
                        text=payload.text,
                        reply_markup=keyboard.reply_keyboard,
                    )
                elif payload.kind == "photo" and payload.file_path is not None:
                    with open(payload.file_path, "rb") as photo_file:
                        await context.bot.send_photo(
                            chat_id=telegram_id,
                            photo=photo_file,
                            caption=payload.text,
                            reply_markup=keyboard.reply_keyboard,
                        )
                elif payload.kind == "video" and payload.file_path is not None:
                    with open(payload.file_path, "rb") as video_file:
                        await context.bot.send_video(
                            chat_id=telegram_id,
                            video=video_file,
                            caption=payload.text,
                            duration=payload.duration,
                            filename=payload.filename,
                            reply_markup=keyboard.reply_keyboard,
                        )
                elif payload.kind == "audio" and payload.file_path is not None:
                    with open(payload.file_path, "rb") as audio_file:
                        await context.bot.send_audio(
                            chat_id=telegram_id,
                            audio=audio_file,
                            caption=payload.text,
                            duration=payload.duration,
                            performer=payload.performer,
                            title=payload.title,
                            filename=payload.filename,
                            reply_markup=keyboard.reply_keyboard,
                        )
                elif payload.kind == "document" and payload.file_path is not None:
                    with open(payload.file_path, "rb") as document_file:
                        await context.bot.send_document(
                            chat_id=telegram_id,
                            document=document_file,
                            caption=payload.text,
                            filename=payload.filename,
                            reply_markup=keyboard.reply_keyboard,
                        )
                else:
                    raise ValueError(f"Неизвестный тип полезной нагрузки [{payload.kind}].")

                logger.info("Рассылка успешно отправлена пользователю %s.", telegram_id)
            except TelegramError as error:
                logger.error(
                    "Не удалось отправить рассылку пользователю %s: %s",
                    telegram_id,
                    error,
                )
                failed_ids.append(telegram_id)

        return failed_ids

    async def __report_broadcast_result(
        self,
        update: Update,
        context: CallbackContext,
        target_ids: list[TelegramId],
        failed_ids: list[TelegramId],
    ) -> None:
        if update.message is None or context.user_data is None:
            return

        recipient_labels: dict[TelegramId, str] = context.user_data.get(self.CTX_RECIPIENT_LABELS, {})
        success_count = len(target_ids) - len(failed_ids)

        if not failed_ids:
            await update.message.reply_text(
                f"Рассылка завершена. Сообщение отправлено {success_count} пользователям."
            )
            return

        failed_text = ", ".join(
            recipient_labels.get(telegram_id, f"<code>{telegram_id}</code>")
            for telegram_id in failed_ids
        )
        await update.message.reply_text(
            (
                f"Рассылка завершена. Сообщение отправлено {success_count} пользователям.\n"
                f"Не удалось отправить: {failed_text}."
            ),
            parse_mode="HTML",
        )

    def __remove_temp_file(self, file_path: str) -> None:
        try:
            os.remove(file_path)
        except OSError:
            logger.warning("Не удалось удалить временный файл рассылки [%s].", file_path)

    def __reset_state(self, context: CallbackContext) -> None:
        if context.user_data is None:
            return

        context.user_data.pop(self.CTX_STAGE, None)
        context.user_data.pop(self.CTX_RECIPIENT_IDS, None)
        context.user_data.pop(self.CTX_RECIPIENT_LABELS, None)
        context.user_data.pop(self.CTX_TARGET_IDS, None)
