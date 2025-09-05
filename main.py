# Загружаем .env ДО импортов модулей приложения
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

from threading import Thread
import uvicorn
from app.config import Settings
from app.db import make_engine, make_session_factory, Base
from app.avito_client import AvitoClient
from app.webhook_server import app
from app.ai_client import make_openai_client
from app.poller import run_polling_loop
import requests
from app.ai_client import make_openai_client, probe_openai
from app.telegram_client import send_tg_message

if __name__ == "__main__":
    cfg = Settings()

    # FastAPI сервер (вебхук)
    def run_api():
        # потише логи uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")

    t = Thread(target=run_api, daemon=True)
    t.start()

    # Подготовка сервисов для поллинга
    engine = make_engine(cfg.db_url, echo=cfg.db_echo)
    Base.metadata.create_all(engine)
    SessionFactory = make_session_factory(engine)
    avito = AvitoClient(cfg.avito_client_id, cfg.avito_client_secret, cfg.avito_user_id)

    oai = None
    if cfg.openai_api_key:
        oai = make_openai_client(
            api_key=cfg.openai_api_key,
        )
    else:
        send_tg_message(cfg.telegram_bot_token, cfg.telegram_chat_id, "🔌 OpenAI is not configured")

    def ask_factory():
        if oai:
            from app.ai_client import ask_gpt
            return lambda text: ask_gpt(text)
        return lambda text: "GPT is not configured"

    # Главный поток — поллинг
    run_polling_loop(
        avito=avito,
        db_session_factory=SessionFactory,
        telegram_bot_token=cfg.telegram_bot_token,
        telegram_chat_id=cfg.telegram_chat_id,
        poll_interval_sec=cfg.poll_interval_sec,
        ask_gpt_fn_factory=ask_factory,
        reply_avito=cfg.reply_back_to_avito,
        only_since_minutes=cfg.poll_only_since_minutes,
    )
