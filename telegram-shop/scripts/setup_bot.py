#!/usr/bin/env python3
"""Настройка Telegram-бота магазина через Bot API (только стандартная библиотека).

Проверяет токен, ставит команды бота, кнопку меню (Mini App/витрина),
включает webhook (или polling), отправляет тестовое сообщение админам.
Бот при старте (bot.py) делает то же самое — этот скрипт нужен, чтобы
настроить и проверить Telegram БЕЗ запуска всего сервера: сразу после
мастера setup-env.sh, до установки зависимостей.

Использование:
    python3 scripts/setup_bot.py                 # всё по .env
    python3 scripts/setup_bot.py --check-only    # только проверить токен (getMe)
    python3 scripts/setup_bot.py --dry-run       # показать запланированные вызовы без сети
    python3 scripts/setup_bot.py --no-test-message
    python3 scripts/setup_bot.py --env /path/.env --timeout 20

Переменные из .env: BOT_TOKEN, WEBAPP_URL, BOT_MODE, WEBHOOK_PATH,
WEBHOOK_SECRET, ADMIN_IDS. Флаги --token/--webapp-url/--bot-mode/--admin-ids
перекрывают .env.
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

TOKEN_RE = re.compile(r"^[0-9]{5,}:[A-Za-z0-9_-]{20,}$")

# Только команды, реально обработанные в bot.py (router.message(Command(...))).
PUBLIC_COMMANDS = [
    ("start", "🛍 Открыть магазин"),
    ("orders", "📦 Мои заказы"),
    ("bonus", "🎁 Бонусы"),
    ("seller", "🏪 Стать продавцом"),
    ("support", "💬 Связь с менеджером"),
    ("faq", "❓ Частые вопросы"),
    ("help", "ℹ️ Помощь"),
]

API = "https://api.telegram.org/bot{token}/{method}"


def parse_env(path):
    """Минимальный парсер KEY=VALUE без зависимостей."""
    data = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip("'\"")
                if k:
                    data[k] = v
    except FileNotFoundError:
        pass
    return data


def mask(token):
    if not token:
        return "не задан"
    return token[:4] + "****" if len(token) > 8 else "****"


def call(token, method, payload, timeout):
    url = API.format(token=token, method=method)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "description": f"HTTP {e.code}"}
    except Exception as e:  # сеть недоступна и т.п.
        return {"ok": False, "description": f"network: {e}"}


def main():
    ap = argparse.ArgumentParser(description="Настройка Telegram-бота магазина")
    ap.add_argument("--env", default=os.path.join(os.path.dirname(__file__), "..", ".env"))
    ap.add_argument("--check-only", action="store_true", help="только проверить токен (getMe)")
    ap.add_argument("--dry-run", action="store_true", help="показать вызовы без сети")
    ap.add_argument("--no-test-message", action="store_true")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--token", default="")
    ap.add_argument("--webapp-url", default="")
    ap.add_argument("--bot-mode", default="", choices=["", "polling", "webhook"])
    ap.add_argument("--admin-ids", default="")
    args = ap.parse_args()

    env = parse_env(args.env)
    token = args.token or env.get("BOT_TOKEN", "")
    webapp = (args.webapp_url or env.get("WEBAPP_URL", "")).rstrip("/")
    mode = (args.bot_mode or env.get("BOT_MODE", "polling")).lower()
    webhook_path = env.get("WEBHOOK_PATH", "/tg/webhook")
    webhook_secret = env.get("WEBHOOK_SECRET", "")
    admins = [x for x in (args.admin_ids or env.get("ADMIN_IDS", "")).replace(" ", "").split(",") if x]

    if not token:
        print("❌ BOT_TOKEN пуст — сначала запустите deploy/setup-env.sh", file=sys.stderr)
        return 2
    if not TOKEN_RE.match(token):
        print("❌ BOT_TOKEN не похож на токен Telegram (ожидается 123456:ABC...)", file=sys.stderr)
        return 2
    if mode not in ("polling", "webhook"):
        print(f"❌ BOT_MODE={mode} недопустим", file=sys.stderr)
        return 2

    plan = ["getMe"]
    plan.append("setMyCommands (%d команд)" % len(PUBLIC_COMMANDS))
    if webapp.startswith("https://"):
        plan.append(f"setChatMenuButton (WebApp: {webapp})")
    else:
        plan.append("setChatMenuButton — ПРОПУСК (нужен https WEBAPP_URL)")
    if mode == "webhook" and webapp.startswith("https://"):
        plan.append(f"setWebhook ({webapp}{webhook_path})")
    else:
        plan.append("deleteWebhook (режим polling)")
    if admins and not args.no_test_message:
        plan.append(f"sendMessage тест админам: {', '.join(admins)}")
    elif not args.no_test_message:
        plan.append("sendMessage — ПРОПУСК (ADMIN_IDS пуст)")

    if args.dry_run:
        print(f"DRY-RUN: токен {mask(token)}, режим {mode}")
        for i, step in enumerate(plan, 1):
            print(f"  {i}. {step}")
        return 0

    fails = 0

    # 1. getMe — проверка токена
    r = call(token, "getMe", {}, args.timeout)
    if not r.get("ok"):
        print(f"❌ getMe: {r.get('description')} — токен неверный или нет сети", file=sys.stderr)
        return 1
    me = r["result"]
    print(f"  ✅ бот: @{me.get('username')} (id {me.get('id')})")
    if args.check_only:
        return 0

    # 2. команды
    r = call(token, "setMyCommands",
             {"commands": [{"command": c, "description": d} for c, d in PUBLIC_COMMANDS]},
             args.timeout)
    print(("  ✅" if r.get("ok") else "  ❌") + f" setMyCommands: {r.get('description', 'ok')}")
    fails += 0 if r.get("ok") else 1

    # 3. кнопка меню
    if webapp.startswith("https://"):
        r = call(token, "setChatMenuButton",
                 {"menu_button": {"type": "web_app", "text": "🛍 Каталог",
                                  "web_app": {"url": webapp}}},
                 args.timeout)
        print(("  ✅" if r.get("ok") else "  ❌") + f" setChatMenuButton: {r.get('description', 'ok')}")
        fails += 0 if r.get("ok") else 1
    else:
        print("  ⚠️ setChatMenuButton пропущен: нужен https WEBAPP_URL")

    # 4. webhook / polling
    if mode == "webhook" and webapp.startswith("https://"):
        payload = {"url": webapp + webhook_path, "drop_pending_updates": True}
        if webhook_secret:
            payload["secret_token"] = webhook_secret
        r = call(token, "setWebhook", payload, args.timeout)
        print(("  ✅" if r.get("ok") else "  ❌") + f" setWebhook: {r.get('description', 'ok')}")
        fails += 0 if r.get("ok") else 1
    else:
        if mode == "webhook":
            print("  ⚠️ webhook невозможен без https WEBAPP_URL — включаю polling")
        r = call(token, "deleteWebhook", {"drop_pending_updates": True}, args.timeout)
        print(("  ✅" if r.get("ok") else "  ❌") + f" deleteWebhook (polling): {r.get('description', 'ok')}")
        fails += 0 if r.get("ok") else 1

    # 5. тестовое сообщение админам
    if admins and not args.no_test_message:
        text = ("✅ Магазин подключён к Telegram.\n"
                f"Бот: @{me.get('username')} · режим: {mode}\n"
                f"Витрина: {webapp or 'локальный запуск'}")
        for admin in admins:
            if not admin.isdigit():
                print(f"  ⚠️ пропущен ADMIN_ID «{admin}»: не число")
                continue
            r = call(token, "sendMessage", {"chat_id": int(admin), "text": text}, args.timeout)
            print(("  ✅" if r.get("ok") else "  ❌") + f" тест админу {admin}: {r.get('description', 'ok')}")
            fails += 0 if r.get("ok") else 1

    if fails:
        print(f"❌ готово с ошибками: {fails}", file=sys.stderr)
        return 1
    print("✅ Telegram настроен")
    return 0


if __name__ == "__main__":
    sys.exit(main())
