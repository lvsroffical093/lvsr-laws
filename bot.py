"""
Бот LVSR-Помощник: показывает кнопку, которая открывает окно с законами (Mini App).

Запуск:  python bot.py
Настройки берутся из файла .env (TOKEN и WEBAPP_URL).
Работает только на стандартной библиотеке Python, ничего ставить не нужно.
"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


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
    "<b>Законы Латвийской Виртуальной Социалистической Республики</b>\n\n"
    "Нажми кнопку ниже, чтобы открыть законы."
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


def laws_keyboard(chat_type, bot_username):
    if chat_type == "private":
        button = {"text": "📜 Открыть законы", "web_app": {"url": WEBAPP_URL}}
    else:
        # В группах Telegram не разрешает кнопку web_app, поэтому ведём в личку с ботом.
        button = {"text": "📜 Открыть законы", "url": f"https://t.me/{bot_username}?start=laws"}
    return {"inline_keyboard": [[button]]}


def setup():
    me = call("getMe")
    # Убираем вебхук, который оставил Puzzle Bot (иначе бот не получит сообщения).
    call("deleteWebhook", drop_pending_updates=False)
    # Кнопка меню слева от поля ввода в личке с ботом.
    call("setChatMenuButton", menu_button={"type": "web_app", "text": "Законы", "web_app": {"url": WEBAPP_URL}})
    call("setMyCommands", commands=[
        {"command": "start", "description": "Открыть законы"},
        {"command": "laws", "description": "Законы ЛВСР"},
    ])
    return me["username"]


def handle(update, bot_username):
    msg = update.get("message")
    if not msg or "text" not in msg:
        return
    command = msg["text"].split()[0].split("@")[0].lower()
    if command not in ("/start", "/laws", "/rules", "/законы"):
        return
    call(
        "sendMessage",
        chat_id=msg["chat"]["id"],
        text=WELCOME,
        parse_mode="HTML",
        reply_markup=laws_keyboard(msg["chat"]["type"], bot_username),
    )


def main():
    bot_username = setup()
    print(f"Бот @{bot_username} запущен. Остановить: Ctrl+C")
    offset = 0
    while True:
        try:
            updates = call("getUpdates", offset=offset, timeout=30, allowed_updates=["message"])
            for upd in updates:
                offset = upd["update_id"] + 1
                try:
                    handle(upd, bot_username)
                except Exception as e:
                    print("Ошибка при ответе:", e)
        except KeyboardInterrupt:
            print("Остановлен.")
            break
        except Exception as e:
            print("Нет связи с Telegram, пробую снова через 5 секунд:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
