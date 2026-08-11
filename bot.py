# bot.py
# Aiogram + Telethon: интерфейс для авторизации номера и сохранения зашифрованной StringSession в Worker
import os
import requests
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from telethon import TelegramClient
from telethon.sessions import StringSession
from cryptography.fernet import Fernet

# Плейсхолдеры: реальные значения задаём в окружении (не в репо)
BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_BOT_TOKEN_HERE")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "PUT_API_HASH_HERE")
WORKER_URL = os.getenv("WORKER_URL", "https://tg-adder.YOUR_ZONE.workers.dev").rstrip("/")
WORKER_API_KEY = os.getenv("WORKER_API_KEY", "PUT_WORKER_API_KEY_HERE")
FERNET_KEY = os.getenv("FERNET_KEY", "PUT_FERNET_KEY_HERE").encode()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
fernet = Fernet(FERNET_KEY)

# Простая state‑логика в памяти (для demo)
pending = {}

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Авторизовать аккаунт", "Удалить сессию")
    kb.add("➕ Добавить группу", "📂 Список групп")
    kb.add("▶️ Запустить парсинг", "🚀 Добавить участников")
    kb.add("📊 Статистика")
    await message.answer("Меню:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "Авторизовать аккаунт")
async def auth_start(message: types.Message):
    await message.answer("Отправь номер в формате +380XXXXXXXXX или +998XXXXXXXXX")
    pending[message.from_user.id] = {"step": "await_phone"}

@dp.message_handler(lambda m: m.text and pending.get(m.from_user.id, {}).get("step") == "await_phone")
async def got_phone(message: types.Message):
    phone = message.text.strip()
    pending[message.from_user.id] = {"step": "await_code", "phone": phone}
    await message.answer("Отправляю код на номер. Жди SMS/Telegram и пришли код сюда.")
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        pending[message.from_user.id].update({"phone_hash": sent.phone_code_hash})
    finally:
        await client.disconnect()

@dp.message_handler(lambda m: m.text and pending.get(m.from_user.id, {}).get("step") == "await_code")
async def got_code(message: types.Message):
    data = pending.get(message.from_user.id)
    code = message.text.strip()
    phone = data["phone"]
    phone_hash = data["phone_hash"]
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    try:
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_hash)
        except Exception as e:
            if 'SESSION_PASSWORD_NEEDED' in str(e):
                await message.answer("У аккаунта включен 2FA. Отправь пароль.")
                pending[message.from_user.id]["step"] = "await_password"
                pending[message.from_user.id]["client"] = client
                return
            else:
                await message.answer(f"Ошибка входа: {e}")
                await client.disconnect()
                pending.pop(message.from_user.id, None)
                return

        string_sess = StringSession.save(client.session)
        token = fernet.encrypt(string_sess.encode()).decode()
        resp = requests.post(f"{WORKER_URL}/store_session", json={"session": token}, headers={"x-api-key": WORKER_API_KEY})
        if resp.status_code == 200:
            await message.answer("Авторизация успешна. Сессия сохранена (зашифрована).")
        else:
            await message.answer("Ошибка сохранения сессии на сервере.")
    finally:
        await client.disconnect()
        pending.pop(message.from_user.id, None)

@dp.message_handler(lambda m: m.text and pending.get(m.from_user.id, {}).get("step") == "await_password")
async def got_password(message: types.Message):
    info = pending[message.from_user.id]
    client = info.get("client")
    password = message.text.strip()
    try:
        await client.sign_in(password=password)
        string_sess = StringSession.save(client.session)
        token = fernet.encrypt(string_sess.encode()).decode()
        resp = requests.post(f"{WORKER_URL}/store_session", json={"session": token}, headers={"x-api-key": WORKER_API_KEY})
        if resp.status_code == 200:
            await message.answer("Авторизация успешна. Сессия сохранена (зашифрована).")
        else:
            await message.answer("Ошибка сохранения сессии на сервере.")
    except Exception as e:
        await message.answer(f"Ошибка 2FA: {e}")
    finally:
        await client.disconnect()
        pending.pop(message.from_user.id, None)

@dp.message_handler(lambda m: m.text == "Удалить сессию")
async def delete_session(message: types.Message):
    resp = requests.post(f"{WORKER_URL}/delete_session", headers={"x-api-key": WORKER_API_KEY})
    if resp.status_code == 200:
        await message.answer("Сессия удалена.")
    else:
        await message.answer("Ошибка удаления сессии.")

@dp.message_handler(lambda m: m.text == "➕ Добавить группу")
async def add_group(message: types.Message):
    await message.answer("Отправь ссылку на группу (t.me/...)")
    pending[message.from_user.id] = {"step": "await_group"}

@dp.message_handler(lambda m: m.text and pending.get(m.from_user.id, {}).get("step") == "await_group")
async def got_group(message: types.Message):
    link = message.text.strip()
    resp = requests.post(f"{WORKER_URL}/add_group", json={"link": link}, headers={"x-api-key": WORKER_API_KEY})
    if resp.status_code == 200:
        await message.answer("Группа добавлена.")
    else:
        await message.answer("Ошибка добавления группы.")
    pending.pop(message.from_user.id, None)

@dp.message_handler(lambda m: m.text == "📂 Список групп")
async def list_groups(message: types.Message):
    resp = requests.get(f"{WORKER_URL}/groups", headers={"x-api-key": WORKER_API_KEY})
    await message.answer(resp.text)

@dp.message_handler(lambda m: m.text == "▶️ Запустить парсинг")
async def run_parser(message: types.Message):
    resp = requests.post(f"{WORKER_URL}/run_parser", headers={"x-api-key": WORKER_API_KEY})
    await message.answer(resp.text)

@dp.message_handler(lambda m: m.text == "🚀 Добавить участников")
async def run_add(message: types.Message):
    resp = requests.post(f"{WORKER_URL}/run_add", headers={"x-api-key": WORKER_API_KEY})
    await message.answer(resp.text)

@dp.message_handler(lambda m: m.text == "📊 Статистика")
async def stats(message: types.Message):
    resp = requests.get(f"{WORKER_URL}/stats", headers={"x-api-key": WORKER_API_KEY})
    await message.answer(resp.text)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
