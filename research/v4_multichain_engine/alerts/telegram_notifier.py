# research/v4_multichain_engine/alerts/telegram_notifier.py

import httpx


class TelegramNotifier:
    """
    Minimal async Telegram notifier.
    Safe: failures never raise to caller.
    """

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    async def send_message(self, text: str) -> None:
        if not self.bot_token or not self.chat_id:
            return

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(self.base_url, json=payload)
        except Exception:
            # Never break engine due to alert failure
            pass