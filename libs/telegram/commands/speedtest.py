import asyncio
import json
from typing import Optional

from .base import *


class SpeedtestCommand(BaseCommand):
    def __init__(
        self,
        database: UserDatabase
    ) -> None:
        super().__init__(database)
        self.command_name = BotCommand.SPEEDTEST

    async def execute(self, update: Update, context: CallbackContext) -> Optional[bool]:
        if update.message is None:
            return

        code, stdout, stderr = await self.__run_speedtest()
        if code != 0 or not stdout:
            await update.message.reply_text(
                "Не удалось выполнить speedtest-cli."
                + (f"\n{stderr}" if stderr else "")
            )
            await self._end_command(update, context)
            return

        message = self.__format_result(stdout)
        await update.message.reply_text(message, parse_mode="HTML")
        await self._end_command(update, context)

    async def __run_speedtest(self) -> tuple[int, str, str]:
        cmds = [
            ["speedtest-cli", "--json"],
            ["speedtest", "--accept-license", "--accept-gdpr", "-f", "json"],
        ]
        for cmd in cmds:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError:
                continue

            stdout, stderr = await proc.communicate()
            if proc.returncode == 0 and stdout:
                return proc.returncode, stdout.decode().strip(), stderr.decode().strip()
        return 127, "", "speedtest-cli не найден в системе."

    def __format_result(self, raw_json: str) -> str:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            return "Не удалось распарсить результат speedtest-cli."

        # speedtest-cli keys
        download = self.__extract_bandwidth(data.get("download") or data.get("downloadBandwidth"))
        upload = self.__extract_bandwidth(data.get("upload") or data.get("uploadBandwidth"))
        ping = data.get("ping")
        if isinstance(ping, dict):
            ping = ping.get("latency")
        server = data.get("server", {})
        sponsor = server.get("sponsor") or server.get("name") or "неизвестно"
        host = server.get("host") or server.get("url") or ""

        download_mbps = self.__to_mbps(download)
        upload_mbps = self.__to_mbps(upload)

        parts = ["⚡ <b>Speedtest</b>"]
        if ping is not None:
            parts.append(f"🏓 Ping: {ping:.1f} ms")
        if download_mbps is not None:
            parts.append(f"⬇️ Download: {download_mbps:.2f} Mbps")
        if upload_mbps is not None:
            parts.append(f"⬆️ Upload: {upload_mbps:.2f} Mbps")
        parts.append(f"🌐 Сервер: {sponsor} {host}")
        return "\n".join(parts)

    def __extract_bandwidth(self, value: Optional[object]) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, dict):
            bandwidth = value.get("bandwidth")
            if bandwidth is None:
                return None
            # Ookla CLI bandwidth is in bytes/second
            return float(bandwidth * 8)
        if isinstance(value, (int, float)):
            # speedtest-cli returns bits/second
            return float(value)
        return None

    def __to_mbps(self, bits_per_second: Optional[float]) -> Optional[float]:
        if bits_per_second is None:
            return None
        return round(bits_per_second / 1_000_000, 2)
