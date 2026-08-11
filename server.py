# server.py
# Telethon worker: читает зашифрованную сессию из Worker (D1), расшифровывает и выполняет парсинг/добавление.
import os
import asyncio
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetParticipantsRequest, InviteToChannelRequest
from telethon.tl.types import ChannelParticipantsSearch
from cryptography.fernet import Fernet

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "PUT_API_HASH_HERE")
WORKER_URL = os.getenv("WORKER_URL", "https://tg-adder.YOUR_ZONE.workers.dev").rstrip("/")
WORKER_API_KEY = os.getenv("WORKER_API_KEY", "PUT_WORKER_API_KEY_HERE")
FERNET_KEY = os.getenv("FERNET_KEY", "PUT_FERNET_KEY_HERE").encode()
fernet = Fernet(FERNET_KEY)

def get_encrypted_session():
    r = requests.get(f"{WORKER_URL}/get_session", headers={"x-api-key": WORKER_API_KEY})
    if r.status_code != 200:
        print("Error fetching session:", r.status_code, r.text)
        return None
    data = r.json()
    return data.get("session")

def decrypt_session(token):
    return fernet.decrypt(token.encode()).decode()

async def parse_groups_and_print():
    enc = get_encrypted_session()
    if not enc:
        print("No session stored")
        return
    session_str = decrypt_session(enc)
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.start()
    # Получаем список групп из Worker
    r = requests.get(f"{WORKER_URL}/groups", headers={"x-api-key": WORKER_API_KEY})
    if r.status_code != 200:
        print("Error fetching groups:", r.status_code, r.text)
        await client.disconnect()
        return
    groups = r.json()
    for g in groups:
        link = g.get('link')
        if not link:
            continue
        try:
            entity = await client.get_entity(link)
            offset = 0
            limit = 200
            while True:
                participants = await client(GetParticipantsRequest(entity, ChannelParticipantsSearch(''), offset, limit, hash=0))
                if not participants.users:
                    break
                for user in participants.users:
                    username = getattr(user, 'username', None)
                    print("Found:", user.id, username)
                    # TODO: сохранить в D1 через Worker или локально
                offset += len(participants.users)
                await asyncio.sleep(1)
        except Exception as e:
            print("Parse error for", link, ":", e)
    await client.disconnect()

async def add_users_to_channel(channel_link, users):
    enc = get_encrypted_session()
    if not enc:
        print("No session")
        return
    session_str = decrypt_session(enc)
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.start()
    for user_id in users:
        try:
            await client(InviteToChannelRequest(channel_link, [user_id]))
            print("Added", user_id)
            await asyncio.sleep(40)  # антибан
        except Exception as e:
            print("Add error", e)
            await asyncio.sleep(5)
    await client.disconnect()

if __name__ == "__main__":
    # Пример: запустить парсинг один раз
    asyncio.run(parse_groups_and_print())
