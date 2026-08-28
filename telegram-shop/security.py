"""Проверка подписи initData Telegram WebApp.

Когда задан BOT_TOKEN, все защищённые API-эндпоинты проверяют, что запрос
действительно пришёл из Telegram Mini App (HMAC-SHA256 по секрету «WebAppData»).
Без токена (локальный превью-режим) проверка пропускается.
"""
import hashlib
import hmac
import json
import time
import urllib.parse

# initData старше суток считаем недействительным
MAX_AUTH_AGE = 24 * 60 * 60


def verify_init_data(init_data: str, bot_token: str):
    """Возвращает (ok: bool, parsed: dict)."""
    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    if not init_data:
        # анонимный доступ (сайт в обычном браузере) — отслеживается по guest_id
        return True, {}
    if not bot_token:
        # dev-режим: токен не задан, проверяем только наличие данных
        return True, parsed

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return False, {}
    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError:
        return False, {}
    if auth_date and time.time() - auth_date > MAX_AUTH_AGE:
        return False, {}

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated, received_hash), parsed


def user_from_init_data(parsed: dict):
    """Извлекает объект пользователя Telegram из initData (или None)."""
    try:
        return json.loads(parsed["user"])
    except (KeyError, ValueError):
        return None
