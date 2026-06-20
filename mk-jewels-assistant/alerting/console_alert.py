import requests
import sys

from config import Config


def _safe_print(message: str):
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(message.encode(encoding, errors="replace").decode(encoding))


class AlertManager:
    def __init__(self, config=Config):
        self.config = config

    def should_alert(self, event: dict) -> bool:
        return event.get("alert_priority") in {"medium", "high"}

    def send_alert(self, salesperson_name: str, event: dict):
        message = self._format_message(salesperson_name, event)
        _safe_print(message)

        if not self.should_alert(event):
            return

        token = self.config.DISCORD_BOT_TOKEN
        channel_id = self.config.DISCORD_CHANNEL_ID
        if not token or not channel_id:
            _safe_print("Warning: Discord alert skipped because bot token or channel ID is missing.")
            return

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
            _safe_print(f"Warning: Discord alert failed: {error}")

    def _format_message(self, salesperson_name: str, event: dict) -> str:
        priority = event.get("alert_priority", "none")
        reasoning = event.get("reasoning", "")
        transcript = event.get("transcript", "")[:120]

        return (
            "🚨 MK Jewels Alert\n"
            f"Salesperson: {salesperson_name}\n"
            f"Priority: {priority}\n"
            f"Signal: {reasoning}\n"
            f'Transcript: "{transcript}..."'
        )
