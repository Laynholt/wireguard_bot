import asyncio
import json
from datetime import date
from typing import Optional, Sequence

from .base import *


class VnstatSummaryCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        super().__init__(database)
        self.command_name = BotCommand.VNSTAT_WEEK

    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        if update.message is None:
            return

        iface = await self.__detect_default_interface()
        if iface is None:
            await update.message.reply_text(
                "Не удалось определить основной сетевой интерфейс."
            )
            await self._end_command(update, context)
            return

        days = await self.__fetch_vnstat_days(iface)
        if days is None or not days:
            await update.message.reply_text(
                f"Не удалось получить данные vnstat для интерфейса {iface}."
            )
            await self._end_command(update, context)
            return

        recent = self.__take_last_days(days, count=7)
        lines = [f"📈 <b>Трафик за 7 дней ({iface})</b>"]
        for d in recent:
            day_date = date(d["date"]["year"], d["date"]["month"], d["date"]["day"])
            rx_bytes = int(d.get("rx", 0))
            tx_bytes = int(d.get("tx", 0))
            rx = self.__format_bytes(rx_bytes)
            tx = self.__format_bytes(tx_bytes)
            total = self.__format_bytes(rx_bytes + tx_bytes)
            lines.append(f"{day_date:%d.%m}: ↓ {rx} ↑ {tx} (Σ {total})")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        await self._end_command(update, context)

    async def __detect_default_interface(self) -> Optional[str]:
        cmds = [
            ["ip", "route", "show", "default"],
            ["ip", "route", "get", "1.1.1.1"],
        ]
        for cmd in cmds:
            code, stdout, _ = await self.__run(cmd)
            if code != 0 or not stdout:
                continue
            tokens = stdout.split()
            if "dev" in tokens:
                dev_index = tokens.index("dev")
                if dev_index + 1 < len(tokens):
                    return tokens[dev_index + 1]
        return None

    async def __fetch_vnstat_days(self, interface: str) -> Optional[Sequence[dict]]:
        commands = [
            ["vnstat", "--json", "d", "-i", interface],
            ["vnstat", "--json", "-i", interface],
        ]
        for cmd in commands:
            code, stdout, stderr = await self.__run(cmd)
            if code != 0 or not stdout:
                continue
            try:
                data = json.loads(stdout)
                for iface in data.get("interfaces", []):
                    if iface.get("name") == interface:
                        traffic = iface.get("traffic", {})
                        return traffic.get("day", [])
            except json.JSONDecodeError:
                continue
        return None

    def __take_last_days(self, days: Sequence[dict], count: int = 7) -> Sequence[dict]:
        sorted_days = sorted(
            days,
            key=lambda d: (
                d.get("date", {}).get("year", 0),
                d.get("date", {}).get("month", 0),
                d.get("date", {}).get("day", 0),
            ),
        )
        return sorted_days[-count:]

    def __format_bytes(self, num_bytes: int) -> str:
        """
        vnstat --json возвращает rx/tx в байтах, форматируем с автоматическим выбором единиц.
        """
        units = ["B", "KiB", "MiB", "GiB", "TiB"]
        value = float(num_bytes)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} TiB"

    async def __run(self, cmd: list[str]) -> tuple[int, str, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return 127, "", f"Command not found: {cmd[0]}"

        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode().strip(), stderr.decode().strip()
