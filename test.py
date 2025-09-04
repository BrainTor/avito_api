import requests, json
from dotenv import load_dotenv
import os

load_dotenv()

BASE = "https://api.avito.ru"
CLIENT_ID = os.getenv("AVITO_CLIENT_ID")
CLIENT_SECRET = os.getenv("AVITO_CLIENT_SECRET")
USER_ID = os.getenv("AVITO_USER_ID")

def get_token():
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,

    }
    r = requests.post(f"{BASE}/token", data=data, timeout=30)  # без слеша в конце — надёжнее
    print("TOKEN STATUS:", r.status_code, r.text[:200])
    r.raise_for_status()
    return r.json()["access_token"]

def list_chats(access_token, limit=20):
    url = f"{BASE}/messenger/v2/accounts/{USER_ID}/chats"
    r = requests.get(url, headers={
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }, params={"limit": limit}, timeout=30)
    print("CHATS STATUS:", r.status_code, r.text[:200])
    r.raise_for_status()
    return r.json()

if __name__ == "__main__":
    token = get_token()
    chats = list_chats(token)
    print(chats)
    
    
    print(token)
