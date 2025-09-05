import requests

_session = requests.Session()
_session.trust_env = False
_NOPX = {"http": None, "https": None}

def send_tg_message(bot_token: str, chat_id: str, text: str, disable_preview: bool = True):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": disable_preview}
    r = _session.post(url, data=data, timeout=15, proxies=_NOPX)
    r.raise_for_status()
    return r.json()
