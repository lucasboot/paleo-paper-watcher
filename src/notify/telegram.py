from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

LOGGER = logging.getLogger(__name__)
TELEGRAM_API_BASE_URL = "https://api.telegram.org"


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    with env_path.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


async def _post_message(
    client: httpx.AsyncClient,
    bot_token: str,
    chat_id: str,
    message: str,
    parse_mode: str | None,
) -> bool:
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    response = await client.post(
        f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/sendMessage",
        json=payload,
    )

    if response.status_code == 200 and response.json().get("ok") is True:
        return True

    return False


def get_chat_ids() -> list[str]:
    raw_value = os.getenv("TELEGRAM_CHAT_IDS", "").strip()
    if not raw_value:
        return []

    return [chat_id.strip() for chat_id in raw_value.split(",") if chat_id.strip()]


async def send_messages(messages: list[str]) -> int:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_ids = get_chat_ids()

    if not bot_token or not chat_ids:
        print("Telegram nao foi configurado. Imprimindo mensagens no terminal.")
        for index, message in enumerate(messages):
            if index > 0:
                print()
            print(message)
        return 0

    sent_count = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for message in messages:
            try:
                delivered_to_all = True
                for chat_id in chat_ids:
                    html_ok = await _post_message(
                        client=client,
                        bot_token=bot_token,
                        chat_id=chat_id,
                        message=message,
                        parse_mode="HTML",
                    )
                    if html_ok:
                        continue

                    plain_ok = await _post_message(
                        client=client,
                        bot_token=bot_token,
                        chat_id=chat_id,
                        message=message,
                        parse_mode=None,
                    )
                    if plain_ok:
                        continue

                    LOGGER.warning("Telegram send failed for chat_id=%s after HTML fallback.", chat_id)
                    delivered_to_all = False
                    break

                if not delivered_to_all:
                    break

                sent_count += 1
            except Exception as exc:
                LOGGER.warning("Telegram send failed: %s", exc)
                break

    return sent_count
