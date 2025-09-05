import time
import logging
from datetime import datetime, timezone, timedelta
from .avito_client import AvitoClient
from .processor import persist_message, notify_and_optionally_ask_gpt

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_polling_loop(
    avito: AvitoClient,
    db_session_factory,
    telegram_bot_token: str,
    telegram_chat_id: str,
    poll_interval_sec: int,
    ask_gpt_fn_factory,     # -> callable(text)->str
    reply_avito: bool = False,
    only_since_minutes: int = 180,  # порог свежести
):
    seen: set[str] = set()
    cycle_count = 0
    logger.info(f"Запуск поллера с интервалом {poll_interval_sec} сек, порог свежести {only_since_minutes} мин")

    while True:
        try:
            cycle_count += 1
            logger.info(f"Начало цикла поллинга #{cycle_count}")
            
            # Проверяем токен каждые 10 циклов
            if cycle_count % 10 == 1:
                if not avito.is_token_valid():
                    logger.warning("Токен недействителен, обновляем...")
                    avito.force_refresh_token()
                else:
                    logger.debug("Токен действителен")
            
            cutoff_dt = datetime.now(tz=timezone.utc) - timedelta(minutes=max(1, only_since_minutes))
            logger.info(f"Порог свежести: {cutoff_dt}")

            offset = 0
            total_chats = 0
            total_messages = 0
            new_messages = 0
            
            while True:
                logger.debug(f"Запрос чатов: offset={offset}")
                # Сначала пробуем получить только чаты с непрочитанными сообщениями
                chats = avito.list_chats(limit=100, offset=offset, unread_only=True)
                items = (chats or {}).get("chats") or []
                
                # Если нет непрочитанных чатов, получаем все чаты для полной проверки
                if not items and offset == 0:
                    logger.debug("Нет непрочитанных чатов, получаем все чаты")
                    chats = avito.list_chats(limit=100, offset=offset, unread_only=False)
                    items = (chats or {}).get("chats") or []
                
                if not items:
                    logger.debug("Больше чатов нет")
                    break
                
                total_chats += len(items)
                logger.info(f"Получено {len(items)} чатов (всего: {total_chats})")

                for ch in items:
                    chat_id = ch.get("id")
                    if not chat_id:
                        continue
                        
                    logger.debug(f"Обработка чата {chat_id}")
                    chat_messages = 0
                    new_in_chat = 0
                    
                    # Получаем только последние сообщения (limit=50 вместо 100)
                    # и проверяем только первые несколько страниц
                    for page in range(3):  # максимум 3 страницы = 150 сообщений
                        moff = page * 50
                        logger.debug(f"Запрос сообщений чата {chat_id}: offset={moff}")
                        msgs = avito.get_messages(chat_id, limit=50, offset=moff)
                        arr = msgs if isinstance(msgs, list) else (msgs.get("messages") or [])
                        if not arr:
                            logger.debug(f"Больше сообщений в чате {chat_id} нет")
                            break
                            
                        chat_messages += len(arr)
                        logger.debug(f"Получено {len(arr)} сообщений из чата {chat_id}")
                        
                        with db_session_factory() as db:
                            for m in arr:
                                mid = m.get("id")
                                if not mid:
                                    continue
                                    
                                if mid in seen:
                                    logger.debug(f"Сообщение {mid} уже обработано")
                                    continue
                                    
                                if persist_message(db, chat_id, m):
                                    seen.add(mid)
                                    new_messages += 1
                                    new_in_chat += 1
                                    logger.info(f"Новое сообщение {mid} в чате {chat_id}")

                                    def ask(text: str) -> str:
                                        return ask_gpt_fn_factory()(text)
                                    def maybe_reply(text: str):
                                        if reply_avito:
                                            avito.send_text(chat_id, text)

                                    notify_and_optionally_ask_gpt(
                                        db, telegram_bot_token, telegram_chat_id, chat_id, m, ask,
                                        maybe_reply if reply_avito else None,
                                        cutoff_dt=cutoff_dt,
                                    )
                                else:
                                    logger.debug(f"Сообщение {mid} не было сохранено (дубликат)")
                        
                        # Если в этой странице не было новых сообщений, 
                        # скорее всего дальше тоже не будет
                        if new_in_chat == 0 and page > 0:
                            logger.debug(f"Нет новых сообщений в чате {chat_id}, пропускаем остальные страницы")
                            break
                    
                    if new_in_chat > 0:
                        logger.info(f"В чате {chat_id} найдено {new_in_chat} новых сообщений")
                    
                    total_messages += chat_messages
                        
                offset += 100

            logger.info(f"Цикл завершен: чатов={total_chats}, сообщений={total_messages}, новых={new_messages}")
            
            # Очищаем кэш seen каждые 100 циклов, чтобы не накапливать слишком много
            if cycle_count % 100 == 0:
                old_size = len(seen)
                seen.clear()
                logger.info(f"Очищен кэш seen (было {old_size} записей)")
            
            time.sleep(poll_interval_sec)
            
        except Exception as e:
            logger.error(f"Ошибка в поллере: {type(e).__name__}: {e}", exc_info=True)
            
            # Если ошибка связана с токеном, попробуем его обновить
            if "token" in str(e).lower() or "unauthorized" in str(e).lower() or "401" in str(e):
                logger.info("Попытка обновления токена Авито")
                try:
                    avito.force_refresh_token()
                    logger.info("Токен успешно обновлен")
                except Exception as token_error:
                    logger.error(f"Не удалось обновить токен: {token_error}")
            
            logger.info(f"Ожидание {poll_interval_sec} сек перед повтором")
            time.sleep(poll_interval_sec)

def test_poller_once(avito: AvitoClient, db_session_factory, telegram_bot_token: str, telegram_chat_id: str, ask_gpt_fn_factory, reply_avito: bool = False, only_since_minutes: int = 180):
    """Тестовая функция для однократного запуска поллера"""
    logger.info("=== ТЕСТОВЫЙ ЗАПУСК ПОЛЛЕРА ===")
    
    try:
        cutoff_dt = datetime.now(tz=timezone.utc) - timedelta(minutes=max(1, only_since_minutes))
        logger.info(f"Порог свежести: {cutoff_dt}")

        offset = 0
        total_chats = 0
        total_messages = 0
        new_messages = 0
        
        while True:
            logger.info(f"Запрос чатов: offset={offset}")
            # Сначала пробуем получить только чаты с непрочитанными сообщениями
            chats = avito.list_chats(limit=100, offset=offset, unread_only=True)
            items = (chats or {}).get("chats") or []
            
            # Если нет непрочитанных чатов, получаем все чаты для полной проверки
            if not items and offset == 0:
                logger.info("Нет непрочитанных чатов, получаем все чаты")
                chats = avito.list_chats(limit=100, offset=offset, unread_only=False)
                items = (chats or {}).get("chats") or []
            
            if not items:
                logger.info("Больше чатов нет")
                break
            
            total_chats += len(items)
            logger.info(f"Получено {len(items)} чатов (всего: {total_chats})")

            for ch in items:
                chat_id = ch.get("id")
                if not chat_id:
                    continue
                    
                logger.info(f"Обработка чата {chat_id}")
                chat_messages = 0
                new_in_chat = 0
                
                # Получаем только последние сообщения (limit=50 вместо 100)
                # и проверяем только первые несколько страниц
                for page in range(3):  # максимум 3 страницы = 150 сообщений
                    moff = page * 50
                    logger.info(f"Запрос сообщений чата {chat_id}: offset={moff}")
                    msgs = avito.get_messages(chat_id, limit=50, offset=moff)
                    arr = msgs if isinstance(msgs, list) else (msgs.get("messages") or [])
                    if not arr:
                        logger.info(f"Больше сообщений в чате {chat_id} нет")
                        break
                        
                    chat_messages += len(arr)
                    logger.info(f"Получено {len(arr)} сообщений из чата {chat_id}")
                    
                    with db_session_factory() as db:
                        for m in arr:
                            mid = m.get("id")
                            if not mid:
                                continue
                                
                            if persist_message(db, chat_id, m):
                                new_messages += 1
                                new_in_chat += 1
                                logger.info(f"НОВОЕ сообщение {mid} в чате {chat_id}")

                                def ask(text: str) -> str:
                                    return ask_gpt_fn_factory()(text)
                                def maybe_reply(text: str):
                                    if reply_avito:
                                        avito.send_text(chat_id, text)

                                notify_and_optionally_ask_gpt(
                                    db, telegram_bot_token, telegram_chat_id, chat_id, m, ask,
                                    maybe_reply if reply_avito else None,
                                    cutoff_dt=cutoff_dt,
                                )
                            else:
                                logger.info(f"Сообщение {mid} уже существует (дубликат)")
                    
                    # Если в этой странице не было новых сообщений, 
                    # скорее всего дальше тоже не будет
                    if new_in_chat == 0 and page > 0:
                        logger.info(f"Нет новых сообщений в чате {chat_id}, пропускаем остальные страницы")
                        break
                
                if new_in_chat > 0:
                    logger.info(f"В чате {chat_id} найдено {new_in_chat} новых сообщений")
                
                total_messages += chat_messages
                    
            offset += 100

        logger.info(f"=== ТЕСТ ЗАВЕРШЕН: чатов={total_chats}, сообщений={total_messages}, новых={new_messages} ===")
        return total_chats, total_messages, new_messages
        
    except Exception as e:
        logger.error(f"Ошибка в тестовом поллере: {type(e).__name__}: {e}", exc_info=True)
        raise
