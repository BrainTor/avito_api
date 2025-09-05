from datetime import datetime
from sqlalchemy import create_engine, BigInteger, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB

class Base(DeclarativeBase):
    pass

class Chat(Base):
    __tablename__ = "chats"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ctx: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    chat_id: Mapped[str] = mapped_column(String, ForeignKey("chats.id"))
    author_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    direction: Mapped[str | None] = mapped_column(String(12), nullable=True)  # in|out|unknown
    type: Mapped[str | None] = mapped_column(String(16), nullable=True)       # text, image, link, ...
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_read: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    chat = relationship("Chat", back_populates="messages")

def make_engine(db_url: str, echo: bool = False):
    return create_engine(db_url, pool_pre_ping=True, echo=echo)

def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
