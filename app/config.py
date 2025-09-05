import os
from pydantic import BaseModel

def _as_bool(v: str | None, default=False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

class Settings(BaseModel):
    # Avito
    avito_client_id: str = os.getenv("AVITO_CLIENT_ID", "")
    avito_client_secret: str = os.getenv("AVITO_CLIENT_SECRET", "")
    avito_user_id: str = os.getenv("AVITO_USER_ID", "")

    # Telegram
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # OpenAI (опционально для "для gpt")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    http_proxy: str = os.getenv("HTTP_PROXY", "") or os.getenv("HTTPS_PROXY", "")
    proxy_host: str = os.getenv("PROXY_HOST", "")
    proxy_port: int = int(os.getenv("PROXY_PORT", "0") or 0)
    proxy_user: str = os.getenv("PROXY_USER", "")
    proxy_pass: str = os.getenv("PROXY_PASS", "")

    # DB
    db_url: str = os.getenv("DB_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/avito_bridge")
    db_echo: bool = _as_bool(os.getenv("DB_ECHO"), False)

    # Поведение
    poll_interval_sec: int = int(os.getenv("POLL_INTERVAL_SEC", "20"))
    poll_only_since_minutes: int = int(os.getenv("POLL_ONLY_SINCE_MINUTES", "180"))  # порог свежести
    reply_back_to_avito: bool = _as_bool(os.getenv("REPLY_BACK_TO_AVITO"), False)
