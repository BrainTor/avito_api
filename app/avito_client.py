import time
import requests
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class AvitoClient:
    BASE = "https://api.avito.ru"
    TIMEOUT = 30

    def __init__(self, client_id: str, client_secret: str, user_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_id = user_id
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._r = requests.Session()
        self._r.trust_env = False
        self._nopx = {"http": None, "https": None}

    def _ensure_token(self):
        if self._token and time.time() < self._token_expires_at - 60:
            logger.debug("Токен еще действителен")
            return
            
        logger.info("Получение нового токена Авито")
        r = self._r.post(
            f"{self.BASE}/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Accept": "application/json"},
            timeout=self.TIMEOUT,
            proxies=self._nopx,
        )
        data = r.json()
        if "access_token" not in data:
            logger.error(f"Ошибка получения токена (status {r.status_code}): {data}")
            raise RuntimeError(f"/token no access_token (status {r.status_code}): {data}")
        
        self._token = data["access_token"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 3600))
        logger.info(f"Токен получен, действителен до {self._token_expires_at}")

    def _headers(self) -> Dict[str, str]:
        self._ensure_token()
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    def list_chats(self, limit: int = 100, offset: int = 0, unread_only: bool = False) -> Dict[str, Any]:
        params = {"limit": limit, "offset": offset}
        if unread_only:
            params["unread_only"] = "true"
        
        logger.debug(f"Запрос списка чатов: {params}")
        r = self._r.get(
            f"{self.BASE}/messenger/v2/accounts/{self.user_id}/chats",
            headers=self._headers(), params=params, timeout=self.TIMEOUT, proxies=self._nopx
        )
        r.raise_for_status()
        data = r.json()
        logger.debug(f"Получено чатов: {len(data.get('chats', []))}")
        return data

    def get_messages(self, chat_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        params = {"limit": limit, "offset": offset}
        
        logger.debug(f"Запрос сообщений чата {chat_id}: {params}")
        r = self._r.get(
            f"{self.BASE}/messenger/v3/accounts/{self.user_id}/chats/{chat_id}/messages/",
            headers=self._headers(), params=params, timeout=self.TIMEOUT, proxies=self._nopx
        )
        r.raise_for_status()
        data = r.json()
        
        # Определяем количество сообщений
        if isinstance(data, list):
            msg_count = len(data)
        else:
            msg_count = len(data.get("messages", []))
        logger.debug(f"Получено сообщений из чата {chat_id}: {msg_count}")
        
        return data

    def chat_read(self, chat_id: str) -> None:
        r = self._r.post(
            f"{self.BASE}/messenger/v1/accounts/{self.user_id}/chats/{chat_id}/read",
            headers=self._headers(), timeout=self.TIMEOUT, proxies=self._nopx
        )
        r.raise_for_status()

    def send_text(self, chat_id: str, text: str) -> Dict[str, Any]:
        headers = self._headers() | {"Content-Type": "application/json"}
        body = {"message": {"text": text}, "type": "text"}
        url_v1 = f"{self.BASE}/messenger/v1/accounts/{self.user_id}/chats/{chat_id}/messages"
        url_v2 = f"{self.BASE}/messenger/v2/accounts/{self.user_id}/chats/{chat_id}/messages"
        
        logger.info(f"Отправка сообщения в чат {chat_id}: {text[:50]}...")
        r = self._r.post(url_v1, headers=headers, json=body, timeout=self.TIMEOUT, proxies=self._nopx)
        if r.status_code in (404, 405):
            logger.debug(f"Попытка через v2 API для чата {chat_id}")
            r = self._r.post(url_v2, headers=headers, json=body, timeout=self.TIMEOUT, proxies=self._nopx)
        r.raise_for_status()
        logger.info(f"Сообщение отправлено в чат {chat_id}")
        return r.json()
    
    def force_refresh_token(self):
        """Принудительно обновить токен"""
        logger.info("Принудительное обновление токена")
        self._token = None
        self._token_expires_at = 0
        self._ensure_token()
    
    def is_token_valid(self) -> bool:
        """Проверить, действителен ли токен"""
        return self._token is not None and time.time() < self._token_expires_at - 60
