import time
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Dict, Any, List, Optional

import requests
import os
from dotenv import load_dotenv


class AvitoClient:
    BASE = "https://api.avito.ru"
    TIMEOUT = 30

    def __init__(self, client_id: str, client_secret: str, user_id: str):
        """
        user_id — числовой ID аккаунта Avito (тот, к которому привязаны объявления/чаты).
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_id = user_id
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ---------- AUTH ----------
    def _ensure_token(self):
        if self._token and time.time() < self._token_expires_at - 60:
            return
        # Исправленный эндпоинт без слеша в конце
        r = requests.post(
            f"{self.BASE}/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=self.TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        # ожидаем { "access_token": "...", "expires_in": 3600, ... }
        self._token = data["access_token"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 3600))

    def _headers(self) -> Dict[str, str]:
        self._ensure_token()
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    # ---------- MESSENGER ----------
    def list_chats(self, limit: int = 50, cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        Возвращает список чатов.
        Эндпоинт: GET /messenger/v2/accounts/{user_id}/chats
        """
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(
            f"{self.BASE}/messenger/v2/accounts/{self.user_id}/chats",
            headers=self._headers(),
            params=params,
            timeout=self.TIMEOUT,
        )
        r.raise_for_status()
        return r.json()

    def get_chat_messages(self, chat_id: str, limit: int = 50, cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        Эндпоинт: GET /messenger/v1/accounts/{user_id}/chats/{chat_id}/messages
        """
        params = {"limit": limit}
        
        if cursor:
            params["cursor"] = cursor
        r = requests.get(
            f"{self.BASE}/messenger/v3/accounts/{self.user_id}/chats/{chat_id}/messages",
            headers=self._headers(),
            timeout=self.TIMEOUT,
            params=params,
        )
        r.raise_for_status()
        return r.json()

    def send_message(self, chat_id: str, text: str) -> Dict[str, Any]:
        """
        Отправка сообщения в чат:
        POST /messenger/v2/accounts/{user_id}/chats/{chat_id}/messages
        body: { "message": { "text": "..." } } или аналог.
        """
        body = {"message": {"text": text}}
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        r = requests.post(
            f"{self.BASE}/messenger/v2/accounts/{self.user_id}/chats/{chat_id}/messages",
            headers=headers,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            timeout=self.TIMEOUT,
        )
        r.raise_for_status()
        return r.json()

    # ---------- AUTOLOAD: отчёты/статусы ----------
    def autoload_reports(self) -> Dict[str, Any]:
        """
        Список отчётов автозагрузки:
        GET /autoload/v1/accounts/{user_id}/reports/
        """
        r = requests.get(
            f"{self.BASE}/autoload/v1/accounts/{self.user_id}/reports/",
            headers=self._headers(),
            timeout=self.TIMEOUT,
        )
        r.raise_for_status()
        return r.json()

    def autoload_last_report(self) -> Dict[str, Any]:
        """
        Последний актуальный отчёт:
        GET /autoload/v1/accounts/{user_id}/reports/last_report/
        """
        r = requests.get(
            f"{self.BASE}/autoload/v1/accounts/{self.user_id}/reports/last_report/",
            headers=self._headers(),
            timeout=self.TIMEOUT,
        )
        r.raise_for_status()
        return r.json()


# ---------- Генерация XML-фида для Автозагрузки ----------
# Форматы фида зависят от категории (Realty, Jobs, Electronics и т.д.).
# В простом случае (товарная категория) нужны теги: Title, Category, Description, Price, Images, Region/City и др.
# Официальные форматы — на autoload.avito.ru/format/... (например, /format/appliances/).
# Ниже — простая заготовка. Обязательно адаптируй под свою категорию!

def build_avito_xml(items: Iterable[Dict[str, Any]]) -> str:
    """
    items: список словарей вида
    {
      "id": "SKU-001",
      "title": "Название",
      "category": "Бытовая электроника",  # проверь нужную категорию и формат
      "description": "Описание товара",
      "price": 1990,
      "region": "Москва",
      "city": "Москва",
      "address": "ул. Пример, 1",
      "images": ["https://example.com/img1.jpg", "https://example.com/img2.jpg"]
    }
    """
    root = ET.Element("Ads", formatVersion="3", target="Avito.ru")
    for it in items:
        ad = ET.SubElement(root, "Ad")
        # Обязательные поля (минимум; проверь по своей категории)
        ET.SubElement(ad, "Id").text = str(it["id"])
        ET.SubElement(ad, "Title").text = it["title"]
        ET.SubElement(ad, "Category").text = it["category"]
        ET.SubElement(ad, "Description").text = it["description"]
        ET.SubElement(ad, "Price").text = str(it["price"])

        # Локация
        loc = ET.SubElement(ad, "Address")
        ET.SubElement(ad, "Region").text = it["region"]
        ET.SubElement(ad, "City").text = it["city"]
        if it.get("address"):
            loc.text = it["address"]

        # Картинки
        if it.get("images"):
            imgs = ET.SubElement(ad, "Images")
            for url in it["images"]:
                ET.SubElement(imgs, "Image", url=url)

        # Добавляй специфичные теги для своей категории:
        # ET.SubElement(ad, "GoodsType").text = "..."  # пример

    # Красивый вывод
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")


if __name__ == "__main__":
    # ==== 1) Чтение/ответ в чатах ====
    load_dotenv()
    AVITO_CLIENT_ID = os.getenv("AVITO_CLIENT_ID")
    AVITO_CLIENT_SECRET = os.getenv("AVITO_CLIENT_SECRET")
    AVITO_USER_ID = os.getenv("AVITO_USER_ID")

    if not all([AVITO_CLIENT_ID, AVITO_CLIENT_SECRET, AVITO_USER_ID]):
        missing = [name for name, val in [
            ("AVITO_CLIENT_ID", AVITO_CLIENT_ID),
            ("AVITO_CLIENT_SECRET", AVITO_CLIENT_SECRET),
            ("AVITO_USER_ID", AVITO_USER_ID),
        ] if not val]
        raise RuntimeError(
            f"Отсутствуют переменные окружения: {', '.join(missing)}. "
            f"Создайте файл .env в корне проекта или задайте их в системе."
        )

    avito = AvitoClient(AVITO_CLIENT_ID, AVITO_CLIENT_SECRET, AVITO_USER_ID)

    # Пример: получить первые чаты
    try:
        chats = avito.list_chats(limit=20)
        #print("Chats:", json.dumps(chats, ensure_ascii=False, indent=2))
        # Если есть чат — прочитать сообщения и ответить
        if chats.get("chats"):
            chat_id = chats["chats"][3]["id"]
            messages = avito.get_chat_messages(chat_id, limit=20)
            print("Messages:", json.dumps(messages, ensure_ascii=False, indent=2))
            # Ответить
            # avito.send_message(chat_id, "Здравствуйте! Готов ответить на вопросы.")
    except requests.HTTPError as e:
        req = getattr(e.response, "request", None)
        method = getattr(req, "method", "?") if req else "?"
        url = getattr(req, "url", "?") if req else "?"
        print("HTTP error:", e.response.status_code, e.response.text)
        print("Request:", method, url)

    # ==== 2) Сборка XML-фида для разных городов/цен ====
    base_item = {
        "id": "SKU-100",
        "title": "Игровая мышь HyperX Pulsefire",
        "category": "Бытовая электроника",  # проверь нужный раздел формата
        "description": "Новая, гарантия. Возможна доставка.",
        "images": ["https://example.com/mouse1.jpg"],
    }

    # Один и тот же товар с разными ценами и городами:
    variants = [
        {**base_item, "id": "SKU-100-MOW", "region": "Москва", "city": "Москва", "price": 2990, "address": "Тверская, 1"},
        {**base_item, "id": "SKU-100-SPB", "region": "Санкт-Петербург", "city": "Санкт-Петербург", "price": 2890, "address": "Невский, 10"},
        {**base_item, "id": "SKU-100-KRD", "region": "Краснодарский край", "city": "Краснодар", "price": 2790, "address": "ул. Северная, 50"},
    ]

    xml_text = build_avito_xml(variants)
    Path("avito_feed.xml").write_text(xml_text, encoding="utf-8")
    print("Сгенерирован фид: avito_feed.xml")

    # Далее:
    # 1) Размести этот XML по постоянной ссылке (https://your-host/avito_feed.xml).
    # 2) В кабинете Авито включи «Автозагрузка» и укажи ссылку на фид + расписание.
    # 3) Через API можно смотреть отчёты автозагрузки:
    #    print(json.dumps(avito.autoload_last_report(), ensure_ascii=False, indent=2))
