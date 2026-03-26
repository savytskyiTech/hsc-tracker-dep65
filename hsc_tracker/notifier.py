from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token
        self._chat_id = chat_id

    def send_message(self, text: str) -> bool:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
        }

        try:
            response = requests.post(url, json=payload, timeout=20)
        except requests.RequestException:
            logger.exception("Failed to call Telegram API")
            return False

        body: dict[str, object] = {}
        try:
            body = response.json()
        except ValueError:
            logger.error(
                "Telegram API returned non-JSON response: status=%s body=%s",
                response.status_code,
                response.text,
            )
            return False

        if response.status_code >= 400 or not body.get("ok", False):
            description = str(body.get("description", "unknown error"))
            error_code = body.get("error_code", response.status_code)
            logger.error("Telegram API error %s: %s", error_code, description)

            if "chat not found" in description.lower():
                logger.error(
                    "CHAT_ID is likely invalid for this bot, or the bot is not added to the chat/group"
                )
                return False

            return False

        logger.info("Telegram notification sent successfully")
        return True
