from fastapi import FastAPI, Request, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from .config import Settings
from .db import make_engine, make_session_factory, Base
from .avito_client import AvitoClient
from .ai_client import make_openai_client, ask_gpt
from .processor import persist_message, notify_and_optionally_ask_gpt

app = FastAPI(title="Avito Webhook Bridge")

settings = Settings()
engine = make_engine(settings.db_url, echo=settings.db_echo)
Base.metadata.create_all(engine)
SessionFactory = make_session_factory(engine)

avito = AvitoClient(settings.avito_client_id, settings.avito_client_secret, settings.avito_user_id)

oai_client = None
if settings.openai_api_key:
    oai_client = make_openai_client(
        api_key=settings.openai_api_key,
    )

@app.post("/avito/webhook")
async def avito_webhook(request: Request, bg: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}

    # Avito иногда заворачивает в { payload: { type: 'message', value: {...} } }
    inner = payload.get("payload") if isinstance(payload, dict) else None
    value = inner.get("value") if isinstance(inner, dict) else (payload if isinstance(payload, dict) else {})
    if not isinstance(value, dict):
        return {"ok": True}

    db: Session = SessionFactory()
    try:
        chat_id = value.get("chat_id")
        if not chat_id:
            return {"ok": True}

        changed = persist_message(db, chat_id, {
            "id": value.get("id"),
            "author_id": value.get("author_id"),
            "direction": "in",
            "type": value.get("type"),
            "content": value.get("content"),
            "created": value.get("created"),
            "is_read": False
        })

        def ask(text: str) -> str:
            if oai_client:
                return ask_gpt(text)
            return "GPT is not configured"

        def reply_avito(answer: str):
            if settings.reply_back_to_avito:
                avito.send_text(chat_id, answer)

        if changed:
            cutoff_dt = datetime.now(tz=timezone.utc) - timedelta(minutes=max(1, settings.poll_only_since_minutes))
            bg.add_task(
                notify_and_optionally_ask_gpt,
                db, settings.telegram_bot_token, settings.telegram_chat_id, chat_id, value,
                ask, reply_avito if settings.reply_back_to_avito else None, cutoff_dt
            )
    finally:
        db.close()

    return {"ok": True}
