"""Alert delivery: console logging, Discord (optional), Telegram (optional).
Configure via DISCORD_BOT_TOKEN/DISCORD_CHANNEL_ID and
TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID in .env.
Leave credentials blank to disable either channel silently.
"""

import requests

from config import Config
from core.logger import get_logger


logger = get_logger(__name__)


class AlertManager:
    def __init__(self, config=Config):
        self.config = config

    def should_alert(self, event: dict) -> bool:
        return event.get("alert_priority") in {"medium", "high"}

    def send_alert(self, salesperson_name: str, event: dict):
        message = self._format_message(salesperson_name, event)
        logger.info("%s", message)

        if not self.should_alert(event):
            return

        token = self.config.DISCORD_BOT_TOKEN
        channel_id = self.config.DISCORD_CHANNEL_ID
        if not token or not channel_id:
            logger.warning("Discord alert skipped because bot token or channel ID is missing.")
        else:
            url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
            headers = {
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
            }

            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json={"content": message},
                    timeout=10,
                )
                response.raise_for_status()
            except requests.RequestException as error:
                logger.error("Discord alert failed: %s", error)

        token = self.config.TELEGRAM_BOT_TOKEN
        chat_id = self.config.TELEGRAM_CHAT_ID
        if not token or not chat_id:
            logger.warning("Telegram alert skipped: credentials not configured")
        else:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
            try:
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                logger.info("Telegram alert sent for %s", salesperson_name)
            except requests.RequestException as error:
                logger.warning("Telegram alert failed: %s", error)

    def _format_message(self, salesperson_name: str, event: dict) -> str:
        priority = event.get("alert_priority", "none")
        reasoning = event.get("reasoning", "")
        transcript = event.get("transcript", "")[:120]

        return (
            "MK Jewels ALERT\n"
            f"Salesperson: {salesperson_name}\n"
            f"Priority: {priority}\n"
            f"Signal: {reasoning}\n"
            f'Transcript: "{transcript}..."'
        )
