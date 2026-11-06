"""Configura el webhook de Telegram usando solo httpx."""

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    secret = os.getenv("TELEGRAM_SECRET", "").strip()
    public_url = os.getenv("PUBLIC_URL", "").strip()
    missing = [
        name
        for name, value in {
            "TELEGRAM_TOKEN": token,
            "TELEGRAM_SECRET": secret,
            "PUBLIC_URL": public_url,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Faltan en .env: {', '.join(missing)}")

    response = httpx.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        data={
            "url": f"{public_url.rstrip('/')}/telegram",
            "secret_token": secret,
        },
        timeout=30.0,
    )
    print(response.text)


if __name__ == "__main__":
    main()
