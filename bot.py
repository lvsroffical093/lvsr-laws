"""
Бот LVSR-Помощник: показывает кнопку, которая открывает окно с законами (Mini App).

Запуск:  python bot.py
Настройки берутся из файла .env (TOKEN и WEBAPP_URL).
Работает только на стандартной библиотеке Python, ничего ставить не нужно.
"""

import json
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG_FILE = HERE / "bot.log"


def log(*parts):
    line = f"[{datetime.now():%d.%m.%Y %H:%M:%S}] " + " ".join(str(p) for p in parts)
    print(line)  # при запуске без окна (pythonw) просто ничего не делает
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 1_000_000:
            LOG_FILE.replace(HERE / "bot.old.log")
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def single_instance():
    # Не даём запустить второго бота одновременно (иначе они мешают друг другу).
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", 47719))
    except OSError:
        log("Бот уже запущен в другом окне или в фоне. Этот экземпляр закрывается.")
        raise SystemExit(0)
    return lock


def load_env():
    env = {}
    path = HERE / ".env"
    if not path.exists():
        raise SystemExit("Нет файла .env. Скопируй .env.example в .env и впиши туда токен.")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


ENV = load_env()
TOKEN = ENV.get("TOKEN", "")
WEBAPP_URL = ENV.get("WEBAPP_URL", "")
if not TOKEN or TOKEN.startswith("вставь"):
    raise SystemExit("В .env не указан TOKEN.")
if not WEBAPP_URL.startswith("https://"):
    raise SystemExit("В .env WEBAPP_URL должен начинаться с https://")

API = f"https://api.telegram.org/bot{TOKEN}/"

WELCOME = (
    "<b>Латвийская Виртуальная Социалистическая Республика</b>\n\n"
    "Нажми кнопку ниже, чтобы открыть меню: законы и конституция."
)


def call(method, **params):
    data = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(API + method, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.load(resp)
    except urllib.error.HTTPError as e:
        result = json.load(e)
    if not result.get("ok"):
        raise RuntimeError(f"{method}: {result.get('description')}")
    return result["result"]


PHOTO_FILE = HERE / "laws.jpg"
PHOTO_ID = None  # после первой загрузки Telegram даёт id картинки, дальше шлём по нему


def call_with_file(method, field, path, **params):
    boundary = "----lvsr" + str(int(time.time() * 1000))
    body = bytearray()
    for key, value in params.items():
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode("utf-8")
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'
             f"Content-Type: image/jpeg\r\n\r\n").encode("utf-8")
    body += path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(API + method, data=bytes(body),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.load(resp)
    except urllib.error.HTTPError as e:
        result = json.load(e)
    if not result.get("ok"):
        raise RuntimeError(f"{method}: {result.get('description')}")
    return result["result"]


def send_laws(chat_id, keyboard):
    global PHOTO_ID
    if not PHOTO_FILE.exists():
        call("sendMessage", chat_id=chat_id, text=WELCOME, parse_mode="HTML", reply_markup=keyboard)
        return
    params = dict(chat_id=chat_id, caption=WELCOME, parse_mode="HTML", reply_markup=keyboard)
    if PHOTO_ID:
        try:
            call("sendPhoto", photo=PHOTO_ID, **params)
            return
        except RuntimeError:
            PHOTO_ID = None  # id устарел — загрузим файл заново
    sent = call_with_file("sendPhoto", "photo", PHOTO_FILE, **params)
    PHOTO_ID = sent["photo"][-1]["file_id"]


def laws_keyboard(chat_type, bot_username):
    if chat_type == "private":
        button = {"text": "📂 Открыть меню", "web_app": {"url": WEBAPP_URL}}
    else:
        # В группах кнопка web_app запрещена, поэтому даём прямую ссылку на Mini App:
        # она открывает окно с законами прямо поверх чата (нужно включить Mini App в BotFather).
        button = {"text": "📂 Открыть меню", "url":f"https://t.me/{bot_username}?startapp"}
    return {"inline_keyboard": [[button]]}


def setup():
    me = call("getMe")
    # Убираем вебхук, который оставил Puzzle Bot (иначе бот не получит сообщения).
    call("deleteWebhook", drop_pending_updates=False)
    # Кнопка меню слева от поля ввода в личке с ботом.
    call("setChatMenuButton", menu_button={"type": "web_app", "text": "Меню", "web_app": {"url": WEBAPP_URL}})
    commands = [{"command": "info", "description": "Меню ЛВСР: законы и конституция"}]
    for scope in ("default", "all_private_chats", "all_group_chats", "all_chat_administrators"):
        call("setMyCommands", commands=commands, scope={"type": scope})
    return me["username"]


CLEANED_CHATS = set()


def clean_chat_commands(chat_id):
    # Puzzle Bot мог оставить в группе свой список команд, который перекрывает наш.
    if chat_id in CLEANED_CHATS:
        return
    CLEANED_CHATS.add(chat_id)
    try:
        call("deleteMyCommands", scope={"type": "chat", "chat_id": chat_id})
    except Exception as e:
        log("Не удалось сбросить старые команды в чате:", e)


def handle(update, bot_username):
    msg = update.get("message")
    if not msg or "text" not in msg:
        return
    if msg["chat"]["type"] != "private":
        clean_chat_commands(msg["chat"]["id"])
    first = msg["text"].split()[0].lower()
    command, _, mention = first.partition("@")
    if mention and mention != bot_username.lower():
        return  # команда адресована другому боту
    is_private = msg["chat"]["type"] == "private"
    # Отвечаем только на /info. /start — лишь в личке (это кнопка «Начать» при первом заходе к боту).
    if not (command == "/info" or (command == "/start" and is_private)):
        return
    send_laws(msg["chat"]["id"], laws_keyboard(msg["chat"]["type"], bot_username))


def main():
    _lock = single_instance()
    # При включении компьютера интернет может появиться не сразу, поэтому ждём.
    while True:
        try:
            bot_username = setup()
            break
        except KeyboardInterrupt:
            return
        except Exception as e:
            log("Не удалось подключиться к Telegram, пробую снова через 15 секунд:", e)
            time.sleep(15)
    log(f"Бот @{bot_username} запущен.")
    offset = 0
    while True:
        try:
            updates = call("getUpdates", offset=offset, timeout=30, allowed_updates=["message"])
            for upd in updates:
                offset = upd["update_id"] + 1
                try:
                    handle(upd, bot_username)
                except Exception as e:
                    log("Ошибка при ответе:", e)
        except KeyboardInterrupt:
            log("Остановлен.")
            break
        except Exception as e:
            log("Нет связи с Telegram, пробую снова через 5 секунд:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
