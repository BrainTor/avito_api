from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from .db import Chat, Message
from .telegram_client import send_tg_message

GPT_TRIGGER = "для gpt"
MAX_TG_LEN = 900  # ограничим размер текста в уведомлении

def _get_text_from_content(content: Dict[str,Any]) -> Optional[str]:
    if not content:
        return None
    if isinstance(content.get("text"), str):
        return content["text"]
    if isinstance(content.get("link"), dict):
        t = content["link"].get("text")
        if isinstance(t, str):
            return t
    return None

def persist_message(db: Session, chat_id: str, msg: Dict[str,Any]) -> bool:
    mid = msg.get("id")
    if not mid:
        return False
    exists = db.get(Message, mid)
    if exists:
        return False

    chat = db.get(Chat, chat_id)
    if not chat:
        chat = Chat(id=chat_id)
        db.add(chat)

    created = msg.get("created")
    created_dt = datetime.fromtimestamp(created, tz=timezone.utc) if isinstance(created, (int,float)) else None
    text = _get_text_from_content(msg.get("content") or {})
    direction = msg.get("direction") or "unknown"

    m = Message(
        id=mid,
        chat_id=chat_id,
        author_id=msg.get("author_id"),
        direction=direction,
        type=msg.get("type"),
        text=text,
        created_ts=created_dt,
        is_read=msg.get("is_read"),
        raw=msg,
    )
    db.add(m)
    db.commit()
    return True

def notify_and_optionally_ask_gpt(
    db: Session,
    bot_token: str,
    chat_id_tg: str,
    avito_chat_id: str,
    msg: Dict[str,Any],
    ask_gpt_fn,          # callable(text)->str
    maybe_reply_avito,   # callable(text)->None or None
    cutoff_dt: Optional[datetime],  # порог свежести (UTC)
):
    # фильтр: только входящие
    if (msg.get("direction") or "").lower() != "in":
        return

    # фильтр по свежести
    if cutoff_dt is not None:
        created = msg.get("created")
        if isinstance(created, (int, float)):
            created_dt = datetime.fromtimestamp(created, tz=timezone.utc)
            if created_dt < cutoff_dt:
                return

    text = _get_text_from_content(msg.get("content") or {}) or "<нет текста>"
    preview = (f"Новое сообщение в Авито\n"
               f"Чат: {avito_chat_id}\n"
               f"Тип: {msg.get('type')}  Направление: {msg.get('direction')}\n"
               f"Текст: {text[:MAX_TG_LEN]}")
    try:
        send_tg_message(bot_token, chat_id_tg, preview)
    except Exception:
        pass

    lower = (text or "").lower()
    if GPT_TRIGGER in lower:
        q = lower.replace(GPT_TRIGGER, "").strip() or text
        try:
            answer = ask_gpt_fn(q)
        except Exception as e:
            answer = f"Ошибка запроса к GPT: {type(e).__name__}: {e}"
        try:
            send_tg_message(bot_token, chat_id_tg, f"GPT ответ:\n{answer[:MAX_TG_LEN]}")
        except Exception:
            pass
        if maybe_reply_avito:
            try:
                maybe_reply_avito(answer)
            except Exception:
                pass
