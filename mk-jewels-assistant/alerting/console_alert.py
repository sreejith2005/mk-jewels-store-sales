"""Alert delivery: console logging, Discord (optional), Telegram (optional).
Configure via DISCORD_BOT_TOKEN/DISCORD_CHANNEL_ID and
TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID in .env.
Leave credentials blank to disable either channel silently.
"""

from html import escape
from typing import Any

import requests

from config import Config
from core.logger import get_logger


logger = get_logger(__name__)


class AlertManager:
    def __init__(self, config=Config):
        self.config = config

    def should_alert(self, event: dict) -> bool:
        return event.get("alert_priority") in {"medium", "high"}

    def send_alert(
        self,
        salesperson_name: str,
        event: dict,
        store_name: str = "MK Jewels",
        event_id: int | None = None,
    ) -> None:
        from storage.db import Database

        priority = str(event.get("alert_priority", "none"))
        message = self._format_message(salesperson_name, event, store_name)
        db = Database()

        def log_delivery(channel: str, status: str, error_text: str | None = None) -> None:
            try:
                db.log_alert(
                    salesperson_name=salesperson_name,
                    store_name=store_name,
                    priority=priority,
                    channel=channel,
                    status=status,
                    event_id=event_id,
                    error_text=error_text,
                )
            except Exception as error:
                logger.warning("Failed to log alert delivery: %s", error)

        try:
            logger.info("%s", self._safe_console_message(message))
            log_delivery("console", "sent")

            if not self.should_alert(event):
                return

            token = self.config.DISCORD_BOT_TOKEN
            channel_id = self.config.DISCORD_CHANNEL_ID
            if not token or not channel_id:
                logger.warning("Discord alert skipped because bot token or channel ID is missing.")
                log_delivery("discord", "skipped", "Discord credentials not configured")
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
                    log_delivery("discord", "sent")
                except requests.RequestException as error:
                    logger.error("Discord alert failed: %s", error)
                    log_delivery("discord", "failed", str(error))

            token = self.config.TELEGRAM_BOT_TOKEN
            chat_id = self.config.TELEGRAM_CHAT_ID
            if not token or not chat_id:
                logger.warning("Telegram alert skipped: credentials not configured")
                log_delivery("telegram", "skipped", "Telegram credentials not configured")
            else:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
                try:
                    response = requests.post(url, json=payload, timeout=10)
                    response.raise_for_status()
                    logger.info("Telegram alert sent for %s", salesperson_name)
                    log_delivery("telegram", "sent")
                except requests.RequestException as error:
                    logger.warning("Telegram alert failed: %s", error)
                    log_delivery("telegram", "failed", str(error))
        finally:
            try:
                db.close()
            except Exception as error:
                logger.warning("Failed to close alert log database connection: %s", error)

    def _format_message(
        self,
        salesperson_name: str,
        event: dict[str, Any],
        store_name: str = "MK Jewels",
    ) -> str:
        priority = str(event.get("alert_priority", "none")).upper()
        priority_emoji = {
            "HIGH": "⛔",
            "MEDIUM": "⚠️",
            "LOW": "ℹ️",
            "NONE": "✅",
        }.get(priority, "✅")
        reasoning = escape(str(event.get("reasoning", "")))
        transcript_preview = escape(str(event.get("transcript", ""))[:150])
        safe_store_name = escape(store_name or "MK Jewels")
        safe_salesperson_name = escape(salesperson_name)

        return (
            "<b>MK Jewels Alert</b>\n"
            f"Store: {safe_store_name}\n"
            f"Salesperson: {safe_salesperson_name}\n"
            f"Priority: {priority_emoji} {priority}\n\n"
            f"Signal: {reasoning}\n\n"
            "Transcript:\n"
            f'"{transcript_preview}"'
        )

    @staticmethod
    def _safe_console_message(message: str) -> str:
        return message.encode("ascii", errors="backslashreplace").decode("ascii")
