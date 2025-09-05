# app/ai_client.py
from typing import Optional
from weakref import proxy
import json
from openai import OpenAI, APIStatusError, APIConnectionError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import requests
import os


def make_openai_client(
    api_key: str,

) -> OpenAI:

    return OpenAI(api_key=api_key)

@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((APIConnectionError, APIStatusError)),
)
def ask_gpt (user_text: str) -> str:
    HOST = os.getenv("PROXY_HOST")
    PORT = os.getenv("PROXY_PORT")
    USER = os.getenv("PROXY_USER")
    PASS = os.getenv("PROXY_PASS")

    url = "https://api.openai.com/v1/responses"
    proxies = {
        "http": f"http://{HOST}:{PORT}:{USER}:{PASS}"
    }
    API_KEY = os.getenv("OPENAI_API_KEY")
    headers = {
    "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
    "model": "gpt-4o-mini",                 
    "input": user_text
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60, proxies=proxies)
    resp.raise_for_status()
    data = resp.json()


    text = data.get("output_text")
    if not text:
        try:
            parts = []
            for item in data.get("output", []):
                if item.get("type") == "message":
                    for c in item.get("content", []):
                        if "text" in c:
                            parts.append(c["text"])
            text = "\n".join(parts).strip()
        except Exception:
            text = json.dumps(data, ensure_ascii=False, indent=2)

    return text

def probe_openai() -> str:
    try:
        return ask_gpt("test")
    except Exception as e:
        return f"ERR: {type(e).__name__}: {e}"
