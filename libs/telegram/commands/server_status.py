import asyncio
from typing import Optional

from .base import *
from libs.core.system_metrics import collect_loadavg, collect_memory, collect_uptime


class ServerStatusCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        super().__init__(database)
        self.command_name = BotCommand.SERVER_STATUS

    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        if update.message is None:
            return

        loop = asyncio.get_running_loop()
        load = await loop.run_in_executor(None, collect_loadavg)
        memory = await loop.run_in_executor(None, collect_memory)
        uptime = await loop.run_in_executor(None, collect_uptime)

        message_lines = ["🖥 <b>Состояние сервера</b>"]

        if load is not None:
            one, five, fifteen, perc_one, perc_five, perc_fifteen = load
            message_lines.append(
                "🧠 CPU load за 1/5/15 минут: "
                f"{one:.2f} / {five:.2f} / {fifteen:.2f} "
                f"({perc_one:.0f}% / {perc_five:.0f}% / {perc_fifteen:.0f}% от числа ядер)"
            )
        else:
            message_lines.append("🧠 CPU load: не удалось получить данные.")

        if memory is not None:
            message_lines.append(
                f"💾 RAM: {memory.ram.used_mb} / {memory.ram.total_mb} MiB ({memory.ram.percent:.0f}%)"
            )

            if memory.swap.total_mb > 0:
                message_lines.append(
                    f"💽 Swap: {memory.swap.used_mb} / {memory.swap.total_mb} MiB ({memory.swap.percent:.0f}%)"
                )
            else:
                message_lines.append("💽 Swap: не настроен")
        else:
            message_lines.append("💾 RAM: не удалось получить данные.")

        if uptime is not None:
            message_lines.append(f"⏱ Uptime: {uptime}")

        await update.message.reply_text("\n".join(message_lines), parse_mode="HTML")
        await self._end_command(update, context)
