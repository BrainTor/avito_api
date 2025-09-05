import os
import requests
import json
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY") 
HOST = os.getenv("PROXY_HOST")
PORT = os.getenv("PROXY_PORT")
USER = os.getenv("PROXY_USER")
PASS = os.getenv("PROXY_PASS")

url = "https://api.openai.com/v1/responses"
proxies = {
        "http": f"http://{HOST}:{PORT}:{USER}:{PASS}"
}
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

payload = {
    "model": "gpt-4o-mini",                 # укажите доступную вам модель
    "input": "Привет! Напиши короткий тост на свадьбу (1-2 предложения)."
}

resp = requests.post(url, headers=headers, json=payload, timeout=60, proxies=proxies)
resp.raise_for_status()
data = resp.json()

# Удобный вывод текста (в Responses API часто есть поле output_text)
text = data.get("output_text")
if not text:
    # резервный разбор, если output_text отсутствует
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

print(text or data)