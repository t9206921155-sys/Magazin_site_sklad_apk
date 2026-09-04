"""Настройки магазина. Значения по умолчанию; секреты — через переменные окружения (файл .env).
Большинство настроек редактируется в админ-панели /admin и хранится в SQLite (data/shop.db).
"""
import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Токен бота от @BotFather. Если пусто — бот отключён, работает сайт и витрина (превью-режим).
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Telegram ID администраторов через запятую, например: 123456789,987654321
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}

# Пароль для входа в веб-админку /admin (по умолчанию admin123 — смените!)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123").strip()

# HTTPS-адрес сайта (для кнопки меню, return_url платёжек и вебхуков бота)
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

# Режим работы бота: polling (по умолчанию) | webhook
BOT_MODE = os.getenv("BOT_MODE", "polling").strip().lower()
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/tg/webhook").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()

# Провайдер оплаты по умолчанию: test | yookassa | tbank | cryptobot | stars
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "test").strip()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()]
METRICS_TOKEN = os.getenv("METRICS_TOKEN", "").strip()
AUTH_RATE_LIMIT = max(1, int(os.getenv("AUTH_RATE_LIMIT", "20")))

DATA_DIR = os.path.join(BASE_DIR, "data")
WEBAPP_DIR = os.path.join(BASE_DIR, "webapp")      # Mini App (Telegram) — /app
SITE_DIR = os.path.join(BASE_DIR, "site")          # сайт-витрина — /
ADMIN_DIR = os.path.join(BASE_DIR, "admin")        # админ-панель (CMS) — /admin
