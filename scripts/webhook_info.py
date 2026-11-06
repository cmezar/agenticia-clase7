"""Consulta el estado del webhook de Telegram usando solo httpx."""

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta TELEGRAM_TOKEN en .env")

    response = httpx.get(
        f"https://api.telegram.org/bot{token}/getWebhookInfo",
        timeout=30.0,
    )
    print(response.text)


if __name__ == "__main__":
    main()
