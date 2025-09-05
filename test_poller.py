#!/usr/bin/env python3
"""
Тестовый скрипт для диагностики поллера Авито
"""
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

import logging
from app.config import Settings
from app.db import make_engine, make_session_factory, Base
from app.avito_client import AvitoClient
from app.ai_client import make_openai_client
from app.poller import test_poller_once

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("=== ДИАГНОСТИКА ПОЛЛЕРА АВИТО ===")
    
    # Загрузка конфигурации
    cfg = Settings()
    logger.info(f"Конфигурация загружена: poll_interval={cfg.poll_interval_sec}с, only_since={cfg.poll_only_since_minutes}мин")
    
    # Инициализация БД
    engine = make_engine(cfg.db_url, echo=cfg.db_echo)
    Base.metadata.create_all(engine)
    SessionFactory = make_session_factory(engine)
    logger.info("База данных инициализирована")
    
    # Инициализация клиента Авито
    avito = AvitoClient(cfg.avito_client_id, cfg.avito_client_secret, cfg.avito_user_id)
    logger.info("Клиент Авито создан")
    
    # Проверка токена
    try:
        avito._ensure_token()
        logger.info("Токен Авито получен успешно")
    except Exception as e:
        logger.error(f"Ошибка получения токена: {e}")
        return
    
    # Инициализация OpenAI (опционально)
    oai = None
    if cfg.openai_api_key:
        try:
            oai = make_openai_client(api_key=cfg.openai_api_key)
            logger.info("OpenAI клиент создан")
        except Exception as e:
            logger.warning(f"Не удалось создать OpenAI клиент: {e}")
    else:
        logger.info("OpenAI не настроен")
    
    def ask_factory():
        if oai:
            from app.ai_client import ask_gpt
            return lambda text: ask_gpt(text)
        return lambda text: "GPT is not configured"
    
    # Запуск тестового поллера
    try:
        logger.info("Запуск тестового поллера...")
        chats, messages, new = test_poller_once(
            avito=avito,
            db_session_factory=SessionFactory,
            telegram_bot_token=cfg.telegram_bot_token,
            telegram_chat_id=cfg.telegram_chat_id,
            ask_gpt_fn_factory=ask_factory,
            reply_avito=cfg.reply_back_to_avito,
            only_since_minutes=cfg.poll_only_since_minutes,
        )
        
        logger.info(f"=== РЕЗУЛЬТАТЫ ===")
        logger.info(f"Обработано чатов: {chats}")
        logger.info(f"Обработано сообщений: {messages}")
        logger.info(f"Новых сообщений: {new}")
        
        if new == 0:
            logger.warning("Новых сообщений не найдено. Возможные причины:")
            logger.warning("1. Все сообщения уже обработаны ранее")
            logger.warning("2. Сообщения старше порога свежести")
            logger.warning("3. Проблема с API Авито")
            logger.warning("4. Проблема с токеном")
        
    except Exception as e:
        logger.error(f"Ошибка в тестовом поллере: {e}", exc_info=True)

if __name__ == "__main__":
    main()
