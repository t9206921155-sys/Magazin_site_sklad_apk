"""Хранилище магазина на SQLite (data/shop.db).

При первом запуске автоматически переносит данные из старых JSON-файлов
(data/products.json, orders.json, settings.json), если они есть.

Помимо товаров/заказов/настроек здесь живут:
  - users  — пользователи Telegram (для рассылок, брошенных корзин)
  - promos — промокоды
  - events — события для аналитики (воронка продаж)
"""
import json
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

import config

_lock = threading.RLock()

# ---------------- умный поиск и ЧПУ ----------------
_RU_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}

def slugify_ru(s: str) -> str:
    out = []
    for ch in str(s).lower():
        if ch in _RU_LAT:
            out.append(_RU_LAT[ch])
        elif ch.isalnum() and ch.isascii():
            out.append(ch)
        elif ch in " -–—":
            out.append("-")
    return "-".join(x for x in "".join(out).split("-") if x)[:80]

CONDITION_LABELS = {"new": "Новое", "used": "Б/у", "defect": "С дефектами"}
CONDITION_SCHEMA = {"new": "https://schema.org/NewCondition",
                    "used": "https://schema.org/UsedCondition",
                    "defect": "https://schema.org/DamagedCondition"}

_SEARCH_SYNONYMS = {
    "телефон": ("смартфон", "мобильный", "мобильник"),
    "смартфон": ("телефон", "мобильный"),
    "мобильный": ("смартфон", "телефон"),
    "ноутбук": ("ноут", "лэптоп"),
    "ноут": ("ноутбук", "лэптоп"),
    "кроссовки": ("кеды", "сникеры", "обувь"),
    "кеды": ("кроссовки", "сникеры"),
    "обувь": ("кроссовки", "кеды", "ботинки"),
    "куртка": ("пуховик", "пальто", "ветровка"),
    "футболка": ("майка", "топ"),
    "платье": ("сарафан",),
    "сумка": ("рюкзак", "клатч"),
    "наушники": ("гарнитура",),
    "зарядка": ("пауэрбанк", "адаптер"),
    "кофеварка": ("кофемашина",),
    "пылесос": ("клинер",),
    "стол": ("тумба", "стеллаж"),
    "кресло": ("стул", "табурет"),
    "лампа": ("светильник", "торшер", "люстра"),
    "часы": ("браслет",),
    "кольцо": ("украшение", "браслет"),
    "серьги": ("украшение",),
    "кулон": ("украшение", "подвеска"),
}

def _norm(s: str) -> str:
    return str(s or "").lower().replace("ё", "е").strip()

def _lev(a: str, b: str) -> int:
    """Расстояние Левенштейна (без библиотек)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]

def _word_similar(w1: str, w2: str, max_d: int) -> bool:
    if w1 == w2:
        return True
    if abs(len(w1) - len(w2)) > max_d:
        return False
    if len(w1) < 4 or len(w2) < 4:
        return False  # короткие слова — только точное совпадение
    return _lev(w1, w2) <= max_d

def search_score(p: dict, query: str) -> int:
    """Оценка релевантности товара запросу (умный поиск с опечатками и синонимами)."""
    q = _norm(query)
    if not q:
        return 0
    q_words = [w for w in q.split() if len(w) >= 2]
    if not q_words:
        return 0
    name = _norm(p.get("name") or "")
    desc = _norm(p.get("description") or "")
    cat = _norm(p.get("category") or "")
    sub = _norm(p.get("subcategory") or "")
    params = " ".join(_norm(str(v)) for v in (p.get("params") or {}).values())
    name_words = set(name.split())
    haystacks = {"name": name, "desc": desc, "cat": cat, "sub": sub, "params": params}

    score = 0
    for qw in q_words:
        best = 0
        variants = {qw, *_SEARCH_SYNONYMS.get(qw, ())}
        for v in variants:
            if name == v:  # точное совпадение всего названия
                best = max(best, 100)
            for hname, hay in haystacks.items():
                if not hay:
                    continue
                weight = {"name": 5, "sub": 4, "cat": 3, "desc": 2, "params": 3}[hname]
                for hw in hay.split():
                    if hw == v:
                        best = max(best, 60 * weight // 5 if hname == "name" else 40)
                    elif hw.startswith(v) and len(v) >= 3:
                        best = max(best, 45 * weight // 5)
                    elif _word_similar(hw, v, 1) and len(v) >= 5:
                        best = max(best, 35)
                    elif _word_similar(hw, v, 2) and len(v) >= 7:
                        best = max(best, 25)
            if v in haystacks["name"] and len(v) >= 3:
                best = max(best, 50)
        score += best
    return score

DB_FILE = os.path.join(config.DATA_DIR, "shop.db")
LEGACY_PRODUCTS = os.path.join(config.DATA_DIR, "products.json")
LEGACY_ORDERS = os.path.join(config.DATA_DIR, "orders.json")
LEGACY_SETTINGS = os.path.join(config.DATA_DIR, "settings.json")

PLACEHOLDER_PHOTO = "/webapp/img/products/placeholder.jpg"

BADGE_LABELS = {"hit": "Хит", "new": "Новинка", "discount": "Скидка", "commission": "Комиссия"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY,
  code TEXT DEFAULT '', name TEXT NOT NULL, category TEXT DEFAULT 'Прочее',
  price INTEGER DEFAULT 0, old_price INTEGER DEFAULT 0, stock INTEGER DEFAULT -1,
  description TEXT DEFAULT '', photo TEXT DEFAULT '', in_stock INTEGER DEFAULT 1,
  badges TEXT DEFAULT '[]', created_at TEXT, updated_at TEXT,
  avito_item_id TEXT DEFAULT '', avito_url TEXT DEFAULT '', avito_status TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS orders(
  id TEXT PRIMARY KEY,
  tg_user_id INTEGER, guest_id TEXT,
  customer TEXT, items TEXT, delivery_method TEXT, delivery TEXT,
  subtotal INTEGER DEFAULT 0, delivery_price INTEGER DEFAULT 0,
  discount INTEGER DEFAULT 0, promo TEXT, total INTEGER DEFAULT 0,
  status TEXT DEFAULT 'pending_payment', payment_method TEXT DEFAULT 'test', payment TEXT,
  synced INTEGER DEFAULT 0, reminded INTEGER DEFAULT 0,
  created_at TEXT, history TEXT
);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS users(
  tg_user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT,
  created_at TEXT, last_activity TEXT
);
CREATE TABLE IF NOT EXISTS promos(
  code TEXT PRIMARY KEY, type TEXT DEFAULT 'percent', value INTEGER DEFAULT 0,
  min_subtotal INTEGER DEFAULT 0, max_uses INTEGER DEFAULT 0, used INTEGER DEFAULT 0,
  enabled INTEGER DEFAULT 1, expires_at TEXT DEFAULT '', description TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, tg_user_id INTEGER, guest_id TEXT,
  type TEXT, payload TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, author TEXT DEFAULT '',
  rating INTEGER DEFAULT 5, text TEXT DEFAULT '', status TEXT DEFAULT 'pending',
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS seller_reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER DEFAULT 0,
  buyer_key TEXT DEFAULT '', buyer_name TEXT DEFAULT '',
  rating INTEGER DEFAULT 5, text TEXT DEFAULT '', status TEXT DEFAULT 'pending',
  created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS posts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE, title TEXT, excerpt TEXT,
  content TEXT, cover TEXT DEFAULT '', published INTEGER DEFAULT 0, created_at TEXT
);
CREATE TABLE IF NOT EXISTS bonus_balances(
  owner_key TEXT PRIMARY KEY, balance INTEGER DEFAULT 0, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS subscribers(
  id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, created_at TEXT
);
CREATE TABLE IF NOT EXISTS sellers(
  id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE, store_name TEXT,
  description TEXT DEFAULT '', tg_user_id INTEGER, phone TEXT DEFAULT '',
  email TEXT DEFAULT '', key TEXT UNIQUE, status TEXT DEFAULT 'pending',
  commission_percent INTEGER DEFAULT 0,
  balance INTEGER DEFAULT 0, total_earned INTEGER DEFAULT 0,
  created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS payouts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER, amount INTEGER,
  status TEXT DEFAULT 'paid', note TEXT DEFAULT '', created_at TEXT
);
CREATE TABLE IF NOT EXISTS wh_users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, login TEXT UNIQUE, pass_hash TEXT,
  name TEXT DEFAULT '', role TEXT DEFAULT 'worker', created_at TEXT
);
CREATE TABLE IF NOT EXISTS wh_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user_name TEXT DEFAULT '',
  action TEXT DEFAULT '', details TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS wh_scans(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user_name TEXT DEFAULT '',
  mode TEXT DEFAULT '', code TEXT DEFAULT '', product_id INTEGER DEFAULT 0,
  qty INTEGER DEFAULT 0, result TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS social_posts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER DEFAULT 0,
  platform TEXT DEFAULT 'telegram', content TEXT DEFAULT '',
  status TEXT DEFAULT 'draft', scheduled_at TEXT DEFAULT '', published_at TEXT DEFAULT '',
  error TEXT DEFAULT '', created_by TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS chat_messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER DEFAULT 0,
  seller_id INTEGER DEFAULT 0, buyer_key TEXT DEFAULT '', buyer_name TEXT DEFAULT '',
  sender TEXT DEFAULT 'buyer', text TEXT DEFAULT '', ts TEXT DEFAULT '',
  read_buyer INTEGER DEFAULT 0, read_seller INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS offers(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER DEFAULT 0,
  seller_id INTEGER DEFAULT 0, buyer_key TEXT DEFAULT '', buyer_name TEXT DEFAULT '',
  proposed_price INTEGER DEFAULT 0, seller_response_price INTEGER DEFAULT 0,
  status TEXT DEFAULT 'pending', message TEXT DEFAULT '',
  seller_note TEXT DEFAULT '', created_at TEXT DEFAULT '', updated_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS comparisons(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_key TEXT DEFAULT '',
  product_ids TEXT DEFAULT '[]', created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS saved_searches(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_key TEXT DEFAULT '',
  query TEXT DEFAULT '', filters TEXT DEFAULT '{}',
  created_at TEXT DEFAULT '', updated_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS boosts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER DEFAULT 0,
  seller_id INTEGER DEFAULT 0, duration_days INTEGER DEFAULT 1,
  started_at TEXT DEFAULT '', expires_at TEXT DEFAULT '',
  price INTEGER DEFAULT 0, status TEXT DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS partner_referrals(
  id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER DEFAULT 0,
  referrer_seller_id INTEGER DEFAULT 0, buyer_key TEXT DEFAULT '',
  order_id TEXT DEFAULT '', commission_amount INTEGER DEFAULT 0, created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS geo_locations(
  id INTEGER PRIMARY KEY AUTOINCREMENT, city TEXT DEFAULT '', region TEXT DEFAULT '',
  lat REAL DEFAULT 0, lng REAL DEFAULT 0, created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS campaigns(
  id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER DEFAULT 0,
  platform TEXT DEFAULT 'yandex', title TEXT DEFAULT '', budget INTEGER DEFAULT 0,
  spent INTEGER DEFAULT 0, status TEXT DEFAULT 'draft', created_at TEXT DEFAULT '',
  creative_url TEXT DEFAULT '', target_city TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS moderation_results(
  id INTEGER PRIMARY KEY AUTOINCREMENT, content_id INTEGER DEFAULT 0,
  content_type TEXT DEFAULT 'product', result TEXT DEFAULT 'pending',
  score REAL DEFAULT 0, details TEXT DEFAULT '', created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS labels(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER DEFAULT 0,
  label_name TEXT DEFAULT '', label_color TEXT DEFAULT '#4f46e5',
  created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS wh_push_subs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER DEFAULT 0,
  sub TEXT DEFAULT '', created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS catalog_cats(
  id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT DEFAULT '',
  subcategory TEXT DEFAULT '', slug TEXT UNIQUE,
  seo_title TEXT DEFAULT '', seo_text TEXT DEFAULT '', sort INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS wh_sessions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER DEFAULT 0,
  secret TEXT UNIQUE, created_at TEXT DEFAULT '', last_used TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS wh_credentials(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER DEFAULT 0,
  credential_id TEXT UNIQUE, public_key TEXT DEFAULT '', sign_count INTEGER DEFAULT 0,
  created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS commission(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER DEFAULT 0,
  name TEXT, description TEXT DEFAULT '', category TEXT DEFAULT 'Комиссия',
  price INTEGER DEFAULT 0, commission_percent INTEGER DEFAULT 15,
  seller_name TEXT DEFAULT '', seller_phone TEXT DEFAULT '',
  photo TEXT DEFAULT '',
  status TEXT DEFAULT 'active',
  sold_order_id TEXT DEFAULT '', sold_at TEXT DEFAULT '',
  payout_amount INTEGER DEFAULT 0, payout_status TEXT DEFAULT 'unpaid',
  created_at TEXT
);
"""

DEFAULT_SETTINGS = {
    "shop_name": "Telegram Shop",
    "currency": "₽",
    "payment_provider": "test",
    "payments": {
        "test": {"enabled": True},
        "transfer": {"enabled": True, "phone": "", "card": "", "bank": "Сбербанк", "name": ""},
        "yookassa": {"enabled": False, "shop_id": "", "secret_key": ""},
        "cryptobot": {"enabled": False, "api_token": "", "asset": "USDT"},
        "stars": {"enabled": True, "rate": 1.0},
        "tbank": {"enabled": False, "terminal_key": "", "password": ""},
    },
    "delivery": {
        "pickup": {"label": "🏬 Самовывоз", "price": 0, "provider": "fixed"},
        "courier": {"label": "🚚 Курьер по городу", "price": 350, "provider": "fixed"},
        "post": {"label": "📦 Почта / СДЭК", "price": 250, "provider": "fixed"},
        "cdek": {"label": "📦 СДЭК (расчёт по API)", "price": 500, "provider": "cdek"},
        "fivepost": {"label": "🅿️ 5POST — постамат/ПВЗ X5", "price": 300, "provider": "fivepost"},
        "yandex": {"label": "🚕 Яндекс Доставка", "price": 450, "provider": "yandex"},
    },
    "cdek": {"enabled": False, "account": "", "password": "", "from_city": 44, "use_test_env": True},
    "fivepost": {"enabled": False, "api_key": "", "warehouse_id": "", "test_mode": True, "brand_name": ""},
    "yandex": {"enabled": False, "token": "", "warehouse_address": "",
               "base_url": "https://b2b.taxi.yandex.net/b2b/cargo/integration", "test_mode": True},
    "free_delivery_from": 0,          # 0 = выключено; иначе порог бесплатной доставки, ₽
    "loyalty": {"enabled": False, "rate_percent": 5},   # % от оплаченного заказа в бонусы
    "marketplace": {"enabled": True, "auto_approve_sellers": True, "commission_percent": 15},
    "cloud": {
        "provider": "s3",                  # storage provider для фото и backup: S3/Yandex
        "db_mode": "vps",                  # vps | supabase_proxy | supabase_direct | mysql
        "enabled": False,                   # использовать внешнее хранилище / внешнюю БД каталога
        "use_cdn": True,                    # подтягивать фото с Object Storage (CDN-URL)
        "url": "",                         # Supabase project URL: https://xxxx.supabase.co
        "key": "",                         # Supabase server key для режима VPS->Supabase
        "public_key": "",                  # Supabase anon/public key для direct-режима из APK/web
        "supabase_schema": "public",       # Supabase schema для REST
        "supabase_table": "products",      # Supabase table/view для каталога
        "bucket": "shop-photos",           # Yandex/S3 bucket для фото
        "photo_prefix": "products",        # папка/префикс для фото
        "catalog_prefix": "catalog",       # папка/префикс для products.json при режиме VPS
        "backup_bucket": "shop-backups",   # Yandex/S3 bucket для backup SQLite
        "backup_prefix": "sqlite",         # папка/префикс для backup SQLite
        "s3_preset": "yandex",             # selectel | cloudru | vk | yandex | minio | custom
        "s3_endpoint": "",                 # S3: https://storage.yandexcloud.net и т.п. (пусто = из пресета)
        "s3_access_key": "",               # S3: access key
        "s3_secret_key": "",               # S3: secret key
        "s3_region": "",                   # S3: регион (пусто = из пресета)
        "mysql_host": "",                  # MySQL: хост (legacy/optional)
        "mysql_port": 3306,                 # MySQL: порт
        "mysql_user": "",                  # MySQL: пользователь
        "mysql_password": "",              # MySQL: пароль
        "mysql_database": "shop",          # MySQL: база
        "mysql_table": "products",         # MySQL: таблица
    },
    "cloud_state": {},                   # {provider, db_mode, photos:{local->url}, last_sync, backup} — состояние синхронизации
    "warehouse": {"publish_on_create": False, "remember_login": True, "auto_sync_cloud": False},
    "warehouse_printers": [
        {"name": "Термопринтер 58×40 мм (PDF)", "width_mm": 58, "height_mm": 40, "format": "pdf", "copies": 1},
        {"name": "Термопринтер 58×30 мм (PDF)", "width_mm": 58, "height_mm": 30, "format": "pdf", "copies": 1},
        {"name": "Zebra — ZPL (58 мм)", "width_mm": 58, "height_mm": 40, "format": "zpl", "copies": 1},
        {"name": "Eltron/ОВЕН — EPL (58 мм)", "width_mm": 58, "height_mm": 40, "format": "epl", "copies": 1},
    ],
    "smtp": {"enabled": False, "host": "", "port": 465, "user": "", "password": "", "from_email": ""},
    "commission_default_percent": 15,   # % комиссии магазина по умолчанию
    "auto_approve_reviews": True,     # публиковать отзывы без модерации
    "abandoned_cart_minutes": 60,     # напоминание о незавершённом заказе через N минут (0 = выкл.)
    "daily_report": True,             # ежедневная сводка админу в Telegram
    "daily_report_hour": 9,
    "timezone": "Europe/Moscow",
    "manager": {"username": "", "text": "Мы на связи! Напишите нам — ответим в течение дня."},
    "social": {
        "auto_post_new": False,        # автопостинг новых товаров
        "telegram_channel": "",        # @channel или -100... (бот должен быть админом)
        "vk_token": "",                # access token VK (права wall, photos)
        "vk_group_id": "",             # id группы VK
        "instagram_token": "",         # long-lived token Meta Graph API
        "instagram_user_id": "",       # Instagram business account id
    },
    "avito": {
        "enabled": False,
        "client_id": "",               # из кабинета Avito (заявка на API)
        "client_secret": "",
        "category_id": 0,              # id категории Avito (кнопка «Категории» в админке)
        "category_name": "Товары",     # для XML-фида автозагрузки
        "goods_type": "Новое",         # Новое | Б/у
        "ad_type": "Товар от производителя",   # Товар от производителя | Товар от частного лица
        "contact_phone": "",
        "address": "",
        "auto_post_new": False,        # выкладывать новые товары автоматически
        "feed_key": None,              # ключ доступа к XML-фиду
    },
    "ai": {
        "enabled": False,
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "tavily_key": "",              # для поиска аналогов в интернете (tavily.com)
    },
    "social_links": {"tg": "", "vk": "", "wa": "", "ok": "", "ig": ""},   # соцсети в футере
    "announcement": "",   # полоса объявления над шапкой (пусто = выключена)
    "faq": [
        {"q": "Как отследить заказ?", "a": "Статус и трек-номер видны в разделе «Мои заказы» в магазине. Мы также присылаем уведомления в чат."},
        {"q": "Как оплатить заказ?", "a": "Картой (ЮKassa или Т-Банк), СБП, криптовалютой или звёздами Telegram — способ выбирается при оформлении."},
        {"q": "Как вернуть товар?", "a": "Напишите нам в течение 14 дней после получения — оформим возврат или обмен."},
    ],
    "texts": {
        "about": "Мы собрали для вас лучшие товары: гаджеты, аксессуары, уютные вещи для дома и идеи для подарков. Работаем с доставкой по всей стране.",
        "delivery": "Доставка: самовывоз, курьер, почта, СДЭК, 5POST и Яндекс Доставка. Стоимость рассчитывается при оформлении. Отправка — 1–2 дня после оплаты.",
        "payments": "Оплата: банковские карты и СБП (ЮKassa, Т-Банк), криптовалюта TON/USDT (CryptoBot), Telegram Stars.",
        "contacts": "Telegram: @telegramshop • Email: shop@example.com • Пн–Вс 10:00–20:00",
    },
    "tariffs": {
        "enabled": True,                  # применять лимиты тарифов
        "commission_percent": 15,         # базовая комиссия площадки (если тарифы включены)
        "escrow_days": 7,                 # холд средств продавца после оплаты, дней (0 = без холда)
        "seller_default_plan": "start",   # план по умолчанию для новых продавцов
        "seller_plans": [
            {"id": "start", "name": "Старт", "price": 0, "max_products": 20, "max_photos": 10,
             "ai_month": 5, "boost_month": 0, "vip_products": 0, "promos_max": 1,
             "commission_discount": 0, "excel": False, "stats": False},
            {"id": "shop", "name": "Магазин", "price": 990, "max_products": 300, "max_photos": 20,
             "ai_month": 50, "boost_month": 5, "vip_products": 2, "promos_max": 10,
             "commission_discount": 0, "excel": True, "stats": True},
            {"id": "business", "name": "Бизнес", "price": 2990, "max_products": 1500, "max_photos": 20,
             "ai_month": 300, "boost_month": 30, "vip_products": 20, "promos_max": -1,
             "commission_discount": 2, "excel": True, "stats": True},
        ],
        "warehouse_plans": [
            {"id": "wh_start", "name": "Старт", "price": 0, "max_positions": 100, "max_users": 1,
             "ai_month": 5, "cloud": False, "excel": False},
            {"id": "wh_shop", "name": "Магазин", "price": 990, "max_positions": 1000, "max_users": 5,
             "ai_month": 50, "cloud": True, "excel": True},
            {"id": "wh_business", "name": "Бизнес", "price": 2990, "max_positions": 10000, "max_users": 20,
             "ai_month": -1, "cloud": True, "excel": True},
        ],
        "promo_services": {"boost_1d": 49, "boost_3d": 99, "boost_7d": 199,
                           "vip_week": 149, "ai_pack_20": 99},
    },
    "1c_token": None,
}

DEMO_PRODUCTS = [
    {"id": 1, "code": "TG-001", "name": "Беспроводные наушники AirSound Pro", "category": "Электроника",
     "price": 2990, "old_price": 0, "stock": 12, "badges": ["hit"],
     "description": "Активное шумоподавление, до 30 часов работы от одного заряда, Bluetooth 5.3.",
     "photo": "/webapp/img/products/p1.jpg", "in_stock": True},
    {"id": 2, "code": "TG-002", "name": "Умные часы FitWatch S8", "category": "Электроника",
     "price": 4490, "old_price": 0, "stock": 7, "badges": [],
     "description": "AMOLED-экран, пульс и SpO2, сон и тренировки, до 14 дней без подзарядки.",
     "photo": "/webapp/img/products/p2.jpg", "in_stock": True},
    {"id": 3, "code": "TG-003", "name": "Портативная колонка Boom Mini", "category": "Электроника",
     "price": 1890, "old_price": 0, "stock": 3, "badges": [],
     "description": "Защита IPX7, 12 часов музыки, мощный бас, Bluetooth 5.0.",
     "photo": "/webapp/img/products/p3.jpg", "in_stock": True},
    {"id": 4, "code": "TG-004", "name": "Термокружка 500 мл", "category": "Дом",
     "price": 1290, "old_price": 1590, "stock": 25, "badges": ["discount"],
     "description": "Нержавеющая сталь, держит тепло до 12 часов, нескользящее покрытие.",
     "photo": "/webapp/img/products/p4.jpg", "in_stock": True},
    {"id": 5, "code": "TG-005", "name": "Керамическая кружка ручной работы", "category": "Дом",
     "price": 690, "old_price": 0, "stock": 5, "badges": [],
     "description": "Уникальная синяя глазурь, объём 350 мл. Каждая — в единственном экземпляре.",
     "photo": "/webapp/img/products/p5.jpg", "in_stock": True},
    {"id": 6, "code": "TG-006", "name": "Плед из мягкого флиса", "category": "Дом",
     "price": 1590, "old_price": 0, "stock": 18, "badges": [],
     "description": "Мягкий и тёплый, 130×170 см, не линяет и не скатывается.",
     "photo": "/webapp/img/products/p6.jpg", "in_stock": True},
    {"id": 7, "code": "TG-007", "name": "Городской рюкзак Urban 25L", "category": "Аксессуары",
     "price": 2490, "old_price": 0, "stock": 2, "badges": [],
     "description": "Отделение для ноутбука 15\", водоотталкивающая ткань, вентилируемая спинка.",
     "photo": "/webapp/img/products/p7.jpg", "in_stock": True},
    {"id": 8, "code": "TG-008", "name": "Набор ароматических свечей", "category": "Подарки",
     "price": 890, "old_price": 0, "stock": 9, "badges": ["new"],
     "description": "3 свечи в стекле: ваниль, лаванда, сандал. Время горения — до 25 часов.",
     "photo": "/webapp/img/products/p8.jpg", "in_stock": True},
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


class Store:
    def __init__(self):
        os.makedirs(config.DATA_DIR, exist_ok=True)
        self._conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with _lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        self._migrate_from_json()
        with _lock:
            self._settings = self._load_settings_from_db()
            self._settings = _deep_merge(DEFAULT_SETTINGS, self._settings)
            if not self._settings.get("1c_token"):
                self._settings["1c_token"] = secrets.token_hex(16)
                self._save_settings_to_db()
            if self._count("SELECT COUNT(*) c FROM products") == 0:
                self._migrate_columns()  # добавляем колонки до вставки демо-товаров
                for p in DEMO_PRODUCTS:
                    self._insert_product(p)
                self._conn.commit()
            else:
                self._migrate_columns()
        with _lock:
            if self._count("SELECT COUNT(*) c FROM wh_users") == 0:
                import hashlib
                self._conn.execute(
                    "INSERT INTO wh_users(login, pass_hash, name, role, created_at) VALUES(?,?,?,?,?)",
                    ("admin", hashlib.sha256(config.ADMIN_PASSWORD.encode()).hexdigest(),
                     "Администратор", "admin", _now_iso()))
                self._conn.commit()
            if not self._settings.get("avito", {}).get("feed_key"):
                self._settings.setdefault("avito", {})["feed_key"] = secrets.token_hex(8)
                self._save_settings_to_db()

    def _migrate_columns(self):
        """Добавляет новые колонки в существующую БД."""
        cols = {r["name"] for r in self._q("PRAGMA table_info(products)")}
        for col, ddl in (
            ("avito_item_id", "TEXT DEFAULT ''"),
            ("avito_url", "TEXT DEFAULT ''"),
            ("avito_status", "TEXT DEFAULT ''"),
        ):
            if col not in cols:
                self._conn.execute(f"ALTER TABLE products ADD COLUMN {col} {ddl}")
        ocols = {r["name"] for r in self._q("PRAGMA table_info(orders)")}
        for col, ddl in (
            ("bonus_spend", "INTEGER DEFAULT 0"),
            ("bonus_accrued", "INTEGER DEFAULT 0"),
            ("bonus_amount", "INTEGER DEFAULT 0"),
            ("owner_key", "TEXT DEFAULT ''"),
            ("sellers_accrued", "INTEGER DEFAULT 0"),
            ("sellers_reverted", "INTEGER DEFAULT 0"),
            ("sellers_escrow", "INTEGER DEFAULT 0"),
            ("sellers_released", "INTEGER DEFAULT 0"),
        ):
            if col not in ocols:
                self._conn.execute(f"ALTER TABLE orders ADD COLUMN {col} {ddl}")
        pcols = {r["name"] for r in self._q("PRAGMA table_info(promos)")}
        if "seller_id" not in pcols:
            self._conn.execute("ALTER TABLE promos ADD COLUMN seller_id INTEGER DEFAULT 0")
        if "seller_id" not in cols:
            self._conn.execute("ALTER TABLE products ADD COLUMN seller_id INTEGER DEFAULT 0")
        for col, ddl in (
            ("purchase_price", "INTEGER DEFAULT 0"),  # закупочная цена (ТЗ)
            ("is_archived", "INTEGER DEFAULT 0"),     # мягкое удаление (архив)
            ("barcode", "TEXT DEFAULT ''"),           # ШК для сканера
            ("storage_location", "TEXT DEFAULT ''"),  # место хранения (стеллаж/коробка)
            ("owner_name", "TEXT DEFAULT ''"),        # владелец товара
            ("photos", "TEXT DEFAULT '[]'"),          # до 20 фото (JSON-список путей)
            ("on_showcase", "INTEGER DEFAULT 1"),     # выставлено на витрину
            ("condition", "TEXT DEFAULT 'new'"),      # состояние: new | used | defect (маркетплейс)
            ("subcategory", "TEXT DEFAULT ''"),       # подкатегория (маркетплейс)
            ("params", "TEXT DEFAULT '{}'"),          # параметры: {бренд, размер, цвет…}
        ):
            if col not in cols:
                self._conn.execute(f"ALTER TABLE products ADD COLUMN {col} {ddl}")
        scols = {r["name"] for r in self._q("PRAGMA table_info(sellers)")}
        for col, ddl in (
            ("plan", "TEXT DEFAULT ''"),                        # тариф продавца (id плана)
            ("held_balance", "INTEGER DEFAULT 0"),              #�ет…}
        ):
            if col not in cols:
                self._conn.execute(f"ALTER TABLE products ADD COLUMN {col} {ddl}")
        scols = {r["name"] for r in self._q("PRAGMA table_info(sellers)")}
        for col, ddl in (
            ("plan", "TEXT DEFAULT ''"),                        # тариф продавца (id плана)
            ("held_balance", "INTEGER DEFAULT 0"),              # средства в холде (эскроу)
            ("ai_used", "INTEGER DEFAULT 0"),                   # ИИ-генераций использовано
            ("ai_month", "TEXT DEFAULT ''"),                    # месяц учёта ИИ (YYYY-MM)
            ("verification_status", "TEXT DEFAULT 'unverified'"),  # unverified|pending|verified|rejected
            ("verification_data", "TEXT DEFAULT '{}'"),         # {inn, owner_name, doc_photo}
        ):
            if col not in scols:
                self._conn.execute(f"ALTER TABLE sellers ADD COLUMN {col} {ddl}")
        self._conn.execute("DROP TABLE IF EXISTS commission")
        self._conn.commit()

    # ------------------------------------------------------------------ sqlite helpers
    def _q(self, sql, params=()):
        return self._conn.execute(sql, params).fetchall()

    def _q1(self, sql, params=()):
        return self._conn.execute(sql, params).fetchone()

    def _count(self, sql, params=()):
        return self._conn.execute(sql, params).fetchone()[0]

    def _migrate_from_json(self):
        """Перенос старых JSON-данных в SQLite (однократно)."""
        if self._count("SELECT COUNT(*) c FROM products") > 0:
            return
        migrated = False
        for p in _load_json(LEGACY_PRODUCTS, []):
            p.setdefault("old_price", 0)
            p.setdefault("stock", -1)
            p.setdefault("badges", [])
            p.setdefault("code", "")
            self._insert_product(p)
            migrated = True
        for o in _load_json(LEGACY_ORDERS, []):
            self._insert_order(o)
            migrated = True
        s = _load_json(LEGACY_SETTINGS, None)
        if s:
            self._conn.execute("INSERT OR REPLACE INTO settings(k, v) VALUES('__settings__', ?)",
                               (json.dumps(s, ensure_ascii=False),))
            migrated = True
        if migrated:
            self._conn.commit()
            print("[store] Данные перенесены из JSON в SQLite (data/shop.db)")

    def _row_to_product(self, r) -> dict:
        p = dict(r)
        try:
            p["badges"] = json.loads(p.get("badges") or "[]")
        except (ValueError, TypeError):
            p["badges"] = []
        try:
            p["photos"] = json.loads(p.get("photos") or "[]")
        except (ValueError, TypeError):
            p["photos"] = []
        try:
            p["params"] = json.loads(p.get("params") or "{}")
        except (ValueError, TypeError):
            p["params"] = {}
        p["on_showcase"] = bool(p.get("on_showcase", 1))
        p["in_stock"] = bool(p.get("in_stock"))
        return p

    def _insert_product(self, p: dict):
        self._conn.execute(
            "INSERT OR REPLACE INTO products(id, code, name, category, price, old_price, stock,"
            " description, photo, in_stock, badges, created_at, updated_at, seller_id, barcode,"
            " storage_location, owner_name, photos, on_showcase, purchase_price, is_archived,"
            " condition, subcategory, params)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (int(p.get("id", 0)), p.get("code", ""), p.get("name", ""), p.get("category", "Прочее"),
             int(p.get("price", 0)), int(p.get("old_price", 0)), int(p.get("stock", -1)),
             p.get("description", ""), p.get("photo", PLACEHOLDER_PHOTO),
             int(bool(p.get("in_stock", True))), json.dumps(p.get("badges", []), ensure_ascii=False),
             p.get("created_at") or _now_iso(), _now_iso(), int(p.get("seller_id") or 0),
             p.get("barcode", ""), p.get("storage_location", ""), p.get("owner_name", ""),
             json.dumps(p.get("photos", []), ensure_ascii=False), int(bool(p.get("on_showcase", 1))),
             int(p.get("purchase_price", 0)), int(bool(p.get("is_archived", 0))),
             p.get("condition", "new"), p.get("subcategory", ""),
             json.dumps(p.get("params", {}), ensure_ascii=False)))

    def _insert_order(self, o: dict):
        self._conn.execute(
            "INSERT OR REPLACE INTO orders(id, tg_user_id, guest_id, customer, items, delivery_method,"
            " delivery, subtotal, delivery_price, discount, promo, total, status, payment_method, payment,"
            " synced, reminded, created_at, history, bonus_spend, bonus_accrued, bonus_amount, owner_key,"
            " sellers_accrued, sellers_reverted, sellers_escrow, sellers_released)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (o["id"], o.get("tg_user_id"), o.get("guest_id"),
             json.dumps(o.get("customer", {}), ensure_ascii=False),
             json.dumps(o.get("items", []), ensure_ascii=False),
             o.get("delivery_method", ""), json.dumps(o.get("delivery", {}), ensure_ascii=False),
             int(o.get("subtotal", 0)), int(o.get("delivery_price", 0)),
             int(o.get("discount", 0)), json.dumps(o.get("promo"), ensure_ascii=False),
             int(o.get("total", 0)), o.get("status", "pending_payment"),
             o.get("payment_method", "test"), json.dumps(o.get("payment"), ensure_ascii=False),
             int(o.get("synced", 0)), int(o.get("reminded", 0)),
             o.get("created_at") or _now_iso(),
             json.dumps(o.get("history", []), ensure_ascii=False),
             int(o.get("bonus_spend", 0)), int(o.get("bonus_accrued", 0)),
             int(o.get("bonus_amount", 0)), o.get("owner_key", ""),
             int(o.get("sellers_accrued", 0)), int(o.get("sellers_reverted", 0)),
             int(o.get("sellers_escrow", 0)), int(o.get("sellers_released", 0))))

    @staticmethod
    def _row_to_order(r) -> dict:
        o = dict(r)
        for f in ("customer", "items", "delivery", "promo", "payment", "history"):
            try:
                o[f] = json.loads(o.get(f) or ("[]" if f in ("items", "history") else "null"))
            except (ValueError, TypeError):
                o[f] = [] if f in ("items", "history") else None
        o["synced"] = bool(o.get("synced"))
        o["reminded"] = bool(o.get("reminded"))
        return o

    def _load_settings_from_db(self) -> dict:
        r = self._q1("SELECT v FROM settings WHERE k='__settings__'")
        if not r:
            return {}
        try:
            return json.loads(r[0])
        except (ValueError, TypeError):
            return {}

    def _save_settings_to_db(self):
        self._conn.execute("INSERT OR REPLACE INTO settings(k, v) VALUES('__settings__', ?)",
                           (json.dumps(self._settings, ensure_ascii=False),))
        self._conn.commit()

    # ---------------- настройки ----------------
    @property
    def settings(self) -> dict:
        return json.loads(json.dumps(self._settings))

    def update_settings(self, patch: dict) -> dict:
        with _lock:
            yk = patch.get("payments", {}).get("yookassa", {})
            if yk and not yk.get("secret_key"):
                yk["secret_key"] = self._settings["payments"]["yookassa"]["secret_key"]
            cb = patch.get("payments", {}).get("cryptobot", {})
            if cb and not cb.get("api_token"):
                cb["api_token"] = self._settings["payments"]["cryptobot"]["api_token"]
            tb = patch.get("payments", {}).get("tbank", {})
            if tb and not tb.get("password"):
                tb["password"] = self._settings["payments"]["tbank"]["password"]
            ai = patch.get("ai", {})
            if ai and not ai.get("api_key"):
                ai["api_key"] = self._settings["ai"]["api_key"]
            if ai and not ai.get("tavily_key"):
                ai["tavily_key"] = self._settings["ai"]["tavily_key"]
            soc = patch.get("social", {})
            if soc and not soc.get("vk_token"):
                soc["vk_token"] = self._settings["social"]["vk_token"]
            av = patch.get("avito", {})
            if av and not av.get("client_secret"):
                av["client_secret"] = self._settings["avito"]["client_secret"]
            if av and not av.get("feed_key"):
                av["feed_key"] = self._settings["avito"].get("feed_key")
            sm = patch.get("smtp", {})
            if sm and not sm.get("password"):
                sm["password"] = self._settings["smtp"]["password"]
            cl = patch.get("cloud", {})
            if cl and not cl.get("key"):
                cl["key"] = self._settings["cloud"]["key"]
            if cl and not cl.get("public_key"):
                cl["public_key"] = self._settings["cloud"].get("public_key", "")
            if cl and not cl.get("s3_secret_key"):
                cl["s3_secret_key"] = self._settings["cloud"]["s3_secret_key"]
            if cl and not cl.get("mysql_password"):
                cl["mysql_password"] = self._settings["cloud"]["mysql_password"]
            so = patch.get("social", {})
            if so and not so.get("instagram_token"):
                so["instagram_token"] = self._settings["social"]["instagram_token"]
            wh = patch.get("warehouse", {})
            if wh and not wh.get("vapid_private"):
                wh["vapid_private"] = self._settings.get("warehouse", {}).get("vapid_private", "")
            if wh and not wh.get("vapid_public"):
                wh["vapid_public"] = self._settings.get("warehouse", {}).get("vapid_public", "")
            self._settings = _deep_merge(self._settings, patch)
            self._save_settings_to_db()
            return self.settings

    def reset_1c_token(self) -> str:
        with _lock:
            self._settings["1c_token"] = secrets.token_hex(16)
            self._save_settings_to_db()
            return self._settings["1c_token"]

    # ---------------- каталог ----------------
    def products(self) -> list:
        return [self._row_to_product(r) for r in self._q("SELECT * FROM products ORDER BY id")]

    def categories(self) -> list:
        cats = []
        for p in self.products():
            c = p.get("category") or "Прочее"
            if c not in cats:
                cats.append(c)
        return cats

    def search_products(self, q: str, limit: int = 60) -> list:
        """Умный поиск по каталогу: опечатки, синонимы, ранжирование. [(id, score)]."""
        q = _norm(q)
        if not q:
            return []
        scored = []
        for p in self.products():
            s = search_score(p, q)
            if s > 0:
                scored.append((int(p["id"]), s))
        scored.sort(key=lambda x: -x[1])
        return scored[:limit]

    def get_product(self, product_id):
        r = self._q1("SELECT * FROM products WHERE id=?", (int(product_id),))
        return self._row_to_product(r) if r else None

    def next_product_id(self) -> int:
        return self._count("SELECT COALESCE(MAX(id), 0)+1 FROM products")

    def _apply_product_fields(self, p: dict, data: dict):
        if "seller_id" in data and data["seller_id"] is not None:
            p["seller_id"] = int(data["seller_id"])
        for f in ("barcode", "storage_location", "owner_name"):
            if f in data and data[f] is not None:
                p[f] = str(data[f]).strip()
        if "photos" in data and isinstance(data["photos"], list):
            p["photos"] = [str(x) for x in data["photos"]][:20]
        if "on_showcase" in data and data["on_showcase"] is not None:
            p["on_showcase"] = bool(data["on_showcase"])
        if "purchase_price" in data and data["purchase_price"] is not None:
            p["purchase_price"] = max(0, int(float(data["purchase_price"])))
        if "is_archived" in data and data["is_archived"] is not None:
            p["is_archived"] = bool(data["is_archived"])
        for f in ("name", "category", "description", "photo", "code", "subcategory"):
            if f in data and data[f] is not None:
                p[f] = str(data[f]).strip() if f != "photo" else str(data[f])
        if "condition" in data and data["condition"] is not None:
            c = str(data["condition"]).strip()
            p["condition"] = c if c in ("new", "used", "defect") else "new"
        if "params" in data and data["params"] is not None:
            pr = data["params"]
            if isinstance(pr, dict):
                p["params"] = {str(k): str(v) for k, v in pr.items() if str(v).strip()}
            else:
                try:
                    p["params"] = {str(k): str(v) for k, v in json.loads(str(pr)).items()}
                except Exception:
                    p["params"] = {}
        for f in ("price", "old_price"):
            if f in data and data[f] is not None:
                p[f] = max(0, int(float(data[f])))
        if "stock" in data and data["stock"] is not None:
            p["stock"] = max(-1, int(float(data["stock"])))
        if "in_stock" in data:
            p["in_stock"] = bool(data["in_stock"])
        if "badges" in data and data["badges"] is not None:
            b = data["badges"]
            p["badges"] = b if isinstance(b, list) else [x for x in str(b).split(",") if x.strip()]

    def add_product(self, data: dict) -> dict:
        with _lock:
            p = {"id": self.next_product_id(), "name": "", "category": "Прочее", "price": 0,
                 "old_price": 0, "stock": -1, "description": "", "photo": PLACEHOLDER_PHOTO,
                 "code": "", "in_stock": True, "badges": [], "created_at": _now_iso()}
            self._apply_product_fields(p, data)
            self._insert_product(p)
            self._conn.commit()
            return {k: v for k, v in p.items() if k != "created_at"}

    def update_product(self, product_id, data: dict):
        with _lock:
            p = self.get_product(product_id)
            if not p:
                return None
            self._apply_product_fields(p, data)
            self._insert_product(p)
            self._conn.commit()
            return dict(p)

    def upsert_product_with_id(self, data: dict) -> dict:
        """Создать или обновить товар с фиксированным id.

        Нужен для direct Supabase режима, когда клиент пишет в Supabase напрямую,
        а VPS зеркалирует те же изменения обратно в локальную SQLite.
        """
        with _lock:
            pid = int(data.get("id") or 0)
            p = self.get_product(pid) if pid else None
            if not p:
                p = {"id": pid or self.next_product_id(), "name": "", "category": "Прочее", "price": 0,
                     "old_price": 0, "stock": -1, "description": "", "photo": PLACEHOLDER_PHOTO,
                     "code": "", "in_stock": True, "badges": [], "created_at": _now_iso()}
            self._apply_product_fields(p, data)
            self._insert_product(p)
            self._conn.commit()
            return dict(p)

    def delete_product(self, product_id) -> bool:
        with _lock:
            self._conn.execute("DELETE FROM products WHERE id=?", (int(product_id),))
            self._conn.commit()
            return self._conn.total_changes > 0

    def upsert_by_code(self, data: dict) -> tuple:
        code = str(data.get("code", "")).strip()
        with _lock:
            target = None
            if code:
                r = self._q1("SELECT * FROM products WHERE code=?", (code,))
                target = self._row_to_product(r) if r else None
            if target is None and data.get("name"):
                r = self._q1("SELECT * FROM products WHERE name=?", (str(data["name"]).strip(),))
                target = self._row_to_product(r) if r else None
            if target:
                self._apply_product_fields(target, data)
                action = "updated"
            else:
                target = {"id": self.next_product_id(), "name": str(data.get("name", "Без названия")),
                          "category": "Прочее", "price": 0, "old_price": 0, "stock": -1,
                          "description": "", "photo": PLACEHOLDER_PHOTO, "code": code,
                          "in_stock": True, "badges": []}
                self._apply_product_fields(target, data)
                action = "created"
            self._insert_product(target)
            self._conn.commit()
            return action, dict(target)

    # ---------------- остатки ----------------
    def _change_stock(self, items: list, delta: int):
        for it in items:
            p = self.get_product(int(it["id"]))
            if not p or p["stock"] < 0:
                continue
            new_stock = max(0, p["stock"] + delta * int(it["qty"]))
            self._conn.execute("UPDATE products SET stock=?, in_stock=?, updated_at=? WHERE id=?",
                               (new_stock, 1 if new_stock > 0 else 0, _now_iso(), int(it["id"])))
        self._conn.commit()

    # ---------------- промокоды ----------------
    def promos(self) -> list:
        return [dict(r) for r in self._q("SELECT * FROM promos ORDER BY code")]

    def create_promo(self, data: dict) -> dict:
        code = str(data.get("code", "")).strip().upper()
        if not code:
            raise ValueError("Укажите код промокода")
        if data.get("type", "percent") not in ("percent", "fixed"):
            raise ValueError("Тип: percent или fixed")
        with _lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO promos(code, type, value, min_subtotal, max_uses, used, enabled, expires_at, description)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (code, data.get("type", "percent"), int(float(data.get("value", 0))),
                 int(float(data.get("min_subtotal", 0))), int(float(data.get("max_uses", 0))),
                 int(data.get("used", 0)), int(bool(data.get("enabled", True))),
                 str(data.get("expires_at", "") or ""), str(data.get("description", "") or "")))
            self._conn.commit()
        return next(p for p in self.promos() if p["code"] == code)

    def delete_promo(self, code: str) -> bool:
        with _lock:
            self._conn.execute("DELETE FROM promos WHERE code=?", (code.upper(),))
            self._conn.commit()
            return self._conn.total_changes > 0

    def validate_promo(self, code: str, subtotal: int) -> dict:
        """Проверка промокода без списания. Возвращает {valid, error?, promo?, discount}."""
        code = str(code or "").strip().upper()
        if not code:
            return {"valid": False, "error": "Введите промокод"}
        r = self._q1("SELECT * FROM promos WHERE code=?", (code,))
        if not r:
            return {"valid": False, "error": "Промокод не найден"}
        p = dict(r)
        if not p["enabled"]:
            return {"valid": False, "error": "Промокод неактивен"}
        if p["expires_at"]:
            try:
                expires = datetime.fromisoformat(p["expires_at"])
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > expires:
                    return {"valid": False, "error": "Срок действия промокода истёк"}
            except ValueError:
                pass
        if p["max_uses"] and p["used"] >= p["max_uses"]:
            return {"valid": False, "error": "Лимит использований исчерпан"}
        if p["min_subtotal"] and int(subtotal) < p["min_subtotal"]:
            return {"valid": False, "error": f"Промокод действует от {p['min_subtotal']} ₽"}
        discount = int(subtotal * p["value"] / 100) if p["type"] == "percent" else min(int(p["value"]), int(subtotal))
        return {"valid": True, "discount": discount,
                "promo": {"code": p["code"], "type": p["type"], "value": p["value"]}}

    def _use_promo(self, code: str):
        self._conn.execute("UPDATE promos SET used=used+1 WHERE code=?", (code.upper(),))
        self._conn.commit()

    # ---------------- заказы ----------------
    def next_order_id(self) -> str:
        return f"ORD-{1000 + self._count('SELECT COUNT(*) c FROM orders') + 1}"

    def create_order(self, items, customer, delivery_method, tg_user_id=None, guest_id=None,
                     payment_method="test", delivery_price=None, promo_code=None, bonus_spend=0) -> dict:
        dm = self._settings["delivery"].get(delivery_method)
        if not dm:
            raise ValueError("Неизвестный способ доставки")
        mp = self._settings.get("marketplace") or {}
        mp_on = bool(mp.get("enabled"))
        default_comm = int(mp.get("commission_percent") or 15)
        lines = []
        for it in items:
            product = self.get_product(int(it["id"]))
            if not product:
                raise ValueError(f"Товар {it['id']} не найден")
            if not product["in_stock"]:
                raise ValueError(f"«{product['name']}» нет в наличии")
            qty = max(1, min(99, int(it["qty"])))
            line = {"id": product["id"], "name": product["name"], "photo": product["photo"],
                    "price": int(product["price"]), "qty": qty, "seller_id": 0}
            if mp_on:
                sid = int(product.get("seller_id") or 0)
                seller = self.get_seller(sid) if sid else None
                if seller and seller["status"] == "active":
                    pct = self.tariff_commission(seller)
                    gross = int(product["price"]) * qty
                    comm = max(0, int(gross * pct / 100))
                    line.update({
                        "seller_id": sid,
                        "seller_name": seller["store_name"],
                        "seller_slug": seller["slug"],
                        "commission_percent": pct,
                        "commission_amount": comm,
                        "seller_net": gross - comm,
                    })
            lines.append(line)
        if not lines:
            raise ValueError("Корзина пуста")

        subtotal = sum(l["price"] * l["qty"] for l in lines)

        discount = 0
        promo_info = None
        if promo_code:
            check = self.validate_promo(promo_code, subtotal)
            if not check["valid"]:
                raise ValueError(check["error"])
            discount = check["discount"]
            promo_info = check["promo"]

        dprice = int(delivery_price) if delivery_price is not None else int(dm["price"])
        free = False
        threshold = int(self._settings.get("free_delivery_from") or 0)
        if threshold > 0 and delivery_method != "pickup" and subtotal >= threshold:
            dprice = 0
            free = True

        platform_commission = sum(l.get("commission_amount", 0) for l in lines)

        # бонусные баллы
        owner_key = f"tg:{tg_user_id}" if tg_user_id else (f"g:{guest_id}" if guest_id else "")
        spend = 0
        if bonus_spend > 0 and owner_key:
            balance = self.bonus_balance(owner_key)
            spend = min(int(bonus_spend), balance, max(0, subtotal - discount))
            if spend > 0:
                self._spend_bonus(owner_key, spend)

        with _lock:
            order = {
                "id": self.next_order_id(),
                "tg_user_id": tg_user_id, "guest_id": guest_id,
                "customer": customer, "delivery_method": delivery_method,
                "delivery": {"label": dm["label"], "price": dprice, "free": free},
                "items": lines, "subtotal": subtotal, "delivery_price": dprice,
                "discount": discount, "promo": promo_info,
                "total": max(0, subtotal - discount - spend + dprice),
                "platform_commission": platform_commission,
                "sellers_accrued": False, "sellers_reverted": False,
                "bonus_spend": spend, "bonus_accrued": False, "bonus_amount": 0,
                "owner_key": owner_key,
                "status": "pending_payment", "payment_method": payment_method,
                "payment": None, "synced": False, "reminded": False,
                "created_at": _now_iso(),
                "history": [{"status": "pending_payment", "at": _now_iso()}],
            }
            self._insert_order(order)
            self._change_stock(items, -1)
            if promo_code:
                self._use_promo(promo_code)
            self.log_event("checkout", tg_user_id, guest_id, {"order_id": order["id"]})
            self._conn.commit()
            return dict(order)

    def get_order(self, order_id: str):
        r = self._q1("SELECT * FROM orders WHERE id=?", (order_id,))
        return self._row_to_order(r) if r else None

    def orders(self, limit: int = 100) -> list:
        rows = self._q("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,))
        return [self._row_to_order(r) for r in rows]

    def orders_for_user(self, tg_user_id=None, guest_id=None) -> list:
        out = []
        for o in self.orders(limit=500):
            if tg_user_id and o.get("tg_user_id") == tg_user_id:
                out.append(o)
            elif guest_id and o.get("guest_id") == guest_id:
                out.append(o)
        return out

    def _update_order(self, o: dict):
        self._insert_order(o)

    def _set_status(self, order: dict, status: str):
        order["status"] = status
        order["history"].append({"status": status, "at": _now_iso()})

    def set_order_status(self, order_id: str, status: str) -> dict:
        with _lock:
            o = self.get_order(order_id)
            if not o:
                return None
            if status == "cancelled" and o["status"] != "cancelled":
                self._change_stock(o["items"], +1)  # возврат остатков
                if o.get("bonus_spend") and o.get("owner_key"):  # возврат бонусов
                    self._add_bonus(o["owner_key"], int(o["bonus_spend"]))
                if o.get("sellers_accrued") and not o.get("sellers_reverted"):
                    for it in o["items"]:  # снятие начислений продавцов (из холда или баланса)
                        if it.get("seller_id") and it.get("seller_net"):
                            if o.get("sellers_escrow"):
                                self._conn.execute(
                                    "UPDATE sellers SET held_balance=MAX(0, held_balance-?),"
                                    " total_earned=MAX(0, total_earned-?), updated_at=? WHERE id=?",
                                    (int(it["seller_net"]), int(it["seller_net"]),
                                     _now_iso(), int(it["seller_id"])))
                            else:
                                self._accrue_seller(it["seller_id"], -int(it["seller_net"]))
                    o["sellers_reverted"] = True
            if status in ("completed", "delivered"):
                # заказ завершён — размораживаем средства продавцов
                self._release_order_held(o)
            self._set_status(o, status)
            self._update_order(o)
            self._conn.commit()
            return dict(o)

    def mark_transfer_reported(self, order_id: str) -> dict:
        """Покупатель сообщил, что перевёл деньги — заказ ждёт ручной проверки админом."""
        with _lock:
            o = self.get_order(order_id)
            if not o:
                return None
            o["payment"] = {"provider": "transfer", "payment_id": None,
                            "status": "verifying", "reported_at": _now_iso()}
            self._update_order(o)
            self._conn.commit()
            return dict(o)

    def mark_payment_pending(self, order_id: str, provider: str, payment_id=None) -> dict:
        with _lock:
            o = self.get_order(order_id)
            if not o:
                return None
            o["payment"] = {"provider": provider, "payment_id": payment_id,
                            "status": "pending", "created_at": _now_iso()}
            self._update_order(o)
            self._conn.commit()
            return dict(o)

    def confirm_payment(self, order_id: str, provider: str, payment_id=None) -> dict:
        with _lock:
            o = self.get_order(order_id)
            if not o:
                return None
            if o["status"] == "paid":
                return dict(o)
            o["payment"] = {"provider": provider, "payment_id": payment_id,
                            "status": "succeeded", "paid_at": _now_iso()}
            self._set_status(o, "paid")
            # начисление бонусов за оплату
            if not o.get("bonus_accrued") and o.get("owner_key"):
                loy = self._settings.get("loyalty") or {}
                if loy.get("enabled"):
                    rate = max(0, int(loy.get("rate_percent") or 0))
                    amount = int(o["total"] * rate / 100)
                    if amount > 0:
                        self._add_bonus(o["owner_key"], amount)
                        o["bonus_accrued"] = True
                        o["bonus_amount"] = amount
            # начисление продавцам маркетплейса (доля продавца после комиссии площадки).
            # При включённом холде (эскроу) средства сначала попадают в held_balance.
            if not o.get("sellers_accrued"):
                t = self._settings.get("tariffs") or {}
                escrow = bool(t.get("enabled") and int(t.get("escrow_days") or 0) > 0)
                for it in o["items"]:
                    if it.get("seller_id") and it.get("seller_net"):
                        if escrow:
                            self._accrue_seller_held(int(it["seller_id"]), int(it["seller_net"]))
                        else:
                            self._accrue_seller(int(it["seller_id"]), int(it["seller_net"]))
                o["sellers_accrued"] = True
                o["sellers_escrow"] = 1 if escrow else 0
            self._update_order(o)
            self.log_event("paid", o.get("tg_user_id"), o.get("guest_id"), {"order_id": order_id})
            self._conn.commit()
            return dict(o)

    def find_by_payment(self, provider: str, payment_id: str):
        for o in self.orders(limit=500):
            if o.get("payment") and o["payment"].get("provider") == provider \
                    and str(o["payment"].get("payment_id")) == str(payment_id):
                return o
        return None

    def mark_synced(self, order_ids: list) -> int:
        with _lock:
            n = 0
            for oid in set(order_ids):
                o = self.get_order(oid)
                if o and not o["synced"]:
                    o["synced"] = True
                    self._update_order(o)
                    n += 1
            if n:
                self._conn.commit()
            return n

    def set_delivery_tracking(self, order_id: str, tracking: str, provider_data=None) -> dict:
        with _lock:
            o = self.get_order(order_id)
            if not o:
                return None
            o["delivery"]["tracking"] = tracking
            if provider_data is not None:
                o["delivery"]["provider_data"] = provider_data
            self._update_order(o)
            self._conn.commit()
            return dict(o)

    def set_payment_method(self, order_id: str, method: str) -> dict:
        with _lock:
            o = self.get_order(order_id)
            if not o:
                return None
            o["payment_method"] = method
            self._update_order(o)
            self._conn.commit()
            return dict(o)

    # ---------------- брошенные корзины ----------------
    def pending_abandoned(self, minutes: int) -> list:
        """Неоплаченные заказы tg-пользователей старше N минут, без напоминания."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        out = []
        for o in self.orders(limit=500):
            if o["status"] != "pending_payment" or not o.get("tg_user_id") or o["reminded"]:
                continue
            try:
                created = datetime.fromisoformat(o["created_at"])
            except (ValueError, TypeError):
                continue
            if created <= cutoff:
                out.append(o)
        return out

    def set_reminded(self, order_id: str):
        with _lock:
            o = self.get_order(order_id)
            if o:
                o["reminded"] = True
                self._update_order(o)
                self._conn.commit()

    # ---------------- пользователи (рассылки) ----------------
    def upsert_user(self, tg_user_id: int, username="", first_name="", last_name=""):
        with _lock:
            self._conn.execute(
                "INSERT INTO users(tg_user_id, username, first_name, last_name, created_at, last_activity)"
                " VALUES(?,?,?,?,?,?) ON CONFLICT(tg_user_id) DO UPDATE SET"
                " username=excluded.username, first_name=excluded.first_name,"
                " last_name=excluded.last_name, last_activity=excluded.last_activity",
                (int(tg_user_id), username or "", first_name or "", last_name or "", _now_iso(), _now_iso()))
            self._conn.commit()

    def all_users(self) -> list:
        return [dict(r) for r in self._q("SELECT * FROM users ORDER BY last_activity DESC")]

    def users_count(self) -> int:
        return self._count("SELECT COUNT(*) c FROM users")

    # ---------------- события (аналитика) ----------------
    def log_event(self, event_type: str, tg_user_id=None, guest_id=None, payload=None):
        with _lock:
            self._conn.execute(
                "INSERT INTO events(ts, tg_user_id, guest_id, type, payload) VALUES(?,?,?,?,?)",
                (_now_iso(), tg_user_id, guest_id, event_type,
                 json.dumps(payload, ensure_ascii=False) if payload else ""))
            self._conn.commit()

    def funnel(self) -> dict:
        out = {}
        for r in self._q("SELECT type, COUNT(*) c FROM events GROUP BY type"):
            out[r["type"]] = r["c"]
        return out

    def sales_by_day(self, days: int = 14) -> list:
        out = []
        now = datetime.now(timezone.utc).date()
        paid = {"paid", "processing", "shipped", "delivered"}
        per_day = {}
        for o in self.orders(limit=5000):
            if o["status"] not in paid:
                continue
            try:
                d = datetime.fromisoformat(o["created_at"]).date()
            except (ValueError, TypeError):
                continue
            per_day[d.isoformat()] = per_day.get(d.isoformat(), 0) + o["total"]
        for i in range(days - 1, -1, -1):
            d = (now - timedelta(days=i)).isoformat()
            out.append({"date": d, "revenue": per_day.get(d, 0)})
        return out

    def top_products(self, limit: int = 5) -> list:
        sold = {}
        for o in self.orders(limit=5000):
            if o["status"] in ("cancelled", "pending_payment"):
                continue
            for i in o["items"]:
                sold[i["name"]] = sold.get(i["name"], 0) + i["qty"]
        return sorted([{"name": k, "qty": v} for k, v in sold.items()],
                      key=lambda x: -x["qty"])[:limit]

    def today_stats(self) -> dict:
        today = datetime.now(timezone.utc).date().isoformat()
        paid = {"paid", "processing", "shipped", "delivered"}
        orders_today = 0
        revenue_today = 0
        for o in self.orders(limit=5000):
            if o["status"] not in paid:
                continue
            try:
                d = datetime.fromisoformat(o["created_at"]).date().isoformat()
            except (ValueError, TypeError):
                continue
            if d == today:
                orders_today += 1
                revenue_today += o["total"]
        return {"orders": orders_today, "revenue": revenue_today}

    # ---------------- Avito ----------------
    def set_avito(self, product_id, item_id: str, url: str, status: str) -> dict:
        with _lock:
            p = self.get_product(product_id)
            if not p:
                return None
            p["avito_item_id"] = str(item_id)
            p["avito_url"] = url
            p["avito_status"] = status
            self._insert_product(p)
            self._conn.commit()
            return dict(p)

    # ---------------- отзывы ----------------
    def add_review(self, product_id: int, author: str, rating: int, text: str) -> dict:
        with _lock:
            status = "approved" if self._settings.get("auto_approve_reviews") else "pending"
            self._conn.execute(
                "INSERT INTO reviews(product_id, author, rating, text, status, created_at)"
                " VALUES(?,?,?,?,?,?)",
                (int(product_id), author[:60], max(1, min(5, int(rating))), text[:1000], status, _now_iso()))
            self._conn.commit()
            r = self._q1("SELECT * FROM reviews ORDER BY id DESC LIMIT 1")
            return dict(r)

    def reviews(self, product_id: int, only_approved: bool = True) -> list:
        sql = "SELECT * FROM reviews WHERE product_id=?"
        if only_approved:
            sql += " AND status='approved'"
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in self._q(sql, (int(product_id),))]

    def all_reviews(self, limit: int = 200) -> list:
        return [dict(r) for r in self._q("SELECT * FROM reviews ORDER BY created_at DESC LIMIT ?", (limit,))]

    def set_review_status(self, review_id: int, status: str) -> bool:
        with _lock:
            self._conn.execute("UPDATE reviews SET status=? WHERE id=?", (status, int(review_id)))
            self._conn.commit()
            return self._conn.total_changes > 0

    def delete_review(self, review_id: int) -> bool:
        with _lock:
            self._conn.execute("DELETE FROM reviews WHERE id=?", (int(review_id),))
            self._conn.commit()
            return self._conn.total_changes > 0

    def review_stats(self, product_id: int) -> dict:
        rows = self._q("SELECT rating FROM reviews WHERE product_id=? AND status='approved'", (int(product_id),))
        if not rows:
            return {"avg": 0, "count": 0}
        vals = [r["rating"] for r in rows]
        return {"avg": round(sum(vals) / len(vals), 1), "count": len(vals)}

    # ---------------- блог ----------------
    def posts(self, published_only: bool = True) -> list:
        sql = "SELECT * FROM posts"
        if published_only:
            sql += " WHERE published=1"
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in self._q(sql)]

    def get_post(self, slug: str):
        r = self._q1("SELECT * FROM posts WHERE slug=?", (slug,))
        return dict(r) if r else None

    def upsert_post(self, data: dict) -> dict:
        with _lock:
            post_id = int(data.get("id") or 0)
            slug = str(data.get("slug") or "").strip()
            existing = None
            if post_id:
                r = self._q1("SELECT * FROM posts WHERE id=?", (post_id,))
                existing = dict(r) if r else None
            if existing is None and slug:
                r = self._q1("SELECT * FROM posts WHERE slug=?", (slug,))
                existing = dict(r) if r else None
            if existing:
                post_id = existing["id"]
                self._conn.execute(
                    "UPDATE posts SET slug=?, title=?, excerpt=?, content=?, cover=?, published=? WHERE id=?",
                    (slug or existing["slug"], str(data.get("title") or existing["title"]),
                     str(data.get("excerpt") or ""), str(data.get("content") or ""),
                     str(data.get("cover") or ""), int(bool(data.get("published", existing.get("published")))),
                     post_id))
            else:
                cur = self._conn.execute(
                    "INSERT INTO posts(slug, title, excerpt, content, cover, published, created_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (slug or ("post-" + secrets.token_hex(4)), str(data.get("title") or "Без названия"),
                     str(data.get("excerpt") or ""), str(data.get("content") or ""),
                     str(data.get("cover") or ""), int(bool(data.get("published", 0))), _now_iso()))
                post_id = cur.lastrowid
            self._conn.commit()
            r = self._q1("SELECT * FROM posts WHERE id=?", (post_id,))
            return dict(r)

    def delete_post(self, post_id: int) -> bool:
        with _lock:
            self._conn.execute("DELETE FROM posts WHERE id=?", (int(post_id),))
            self._conn.commit()
            return self._conn.total_changes > 0

    # ---------------- бонусные баллы ----------------
    def bonus_balance(self, owner_key: str) -> int:
        r = self._q1("SELECT balance FROM bonus_balances WHERE owner_key=?", (owner_key,))
        return int(r["balance"]) if r else 0

    def _add_bonus(self, owner_key: str, amount: int):
        if not owner_key or amount <= 0:
            return
        self._conn.execute(
            "INSERT INTO bonus_balances(owner_key, balance, updated_at) VALUES(?,?,?)"
            " ON CONFLICT(owner_key) DO UPDATE SET balance=balance+excluded.balance, updated_at=excluded.updated_at",
            (owner_key, int(amount), _now_iso()))
        self._conn.commit()

    def _spend_bonus(self, owner_key: str, amount: int):
        if not owner_key or amount <= 0:
            return
        self._conn.execute(
            "INSERT INTO bonus_balances(owner_key, balance, updated_at) VALUES(?,0,?)"
            " ON CONFLICT(owner_key) DO NOTHING",
            (owner_key, _now_iso()))
        self._conn.execute(
            "UPDATE bonus_balances SET balance=MAX(0, balance-?), updated_at=? WHERE owner_key=?",
            (int(amount), _now_iso(), owner_key))
        self._conn.commit()

    def add_bonus_manual(self, owner_key: str, amount: int) -> int:
        with _lock:
            self._add_bonus(owner_key, amount)
            return self.bonus_balance(owner_key)

    # ---------------- комиссионные товары ----------------
    def commission_items(self, status: str = "") -> list:
        sql = "SELECT * FROM commission"
        if status:
            sql += " WHERE status=?"
            return [dict(r) for r in self._q(sql + " ORDER BY created_at DESC", (status,))]
        return [dict(r) for r in self._q(sql + " ORDER BY created_at DESC")]

    def get_commission(self, commission_id: int):
        r = self._q1("SELECT * FROM commission WHERE id=?", (int(commission_id),))
        return dict(r) if r else None

    def add_commission(self, data: dict, create_product: bool = True) -> dict:
        """Создаёт комиссионный товар. При create_product=True создаёт товар в каталоге."""
        percent = int(data.get("commission_percent") or
                      self._settings.get("commission_default_percent") or 15)
        with _lock:
            product_id = 0
            if create_product:
                badges = list(data.get("badges") or [])
                if "commission" not in badges:
                    badges.append("commission")
                product = self.add_product({
                    "name": str(data.get("name") or "Комиссионный товар"),
                    "category": str(data.get("category") or "Комиссия"),
                    "price": int(float(data.get("price") or 0)),
                    "description": str(data.get("description") or ""),
                    "photo": str(data.get("photo") or PLACEHOLDER_PHOTO),
                    "stock": 1,
                    "badges": badges,
                })
                product_id = product["id"]
            cur = self._conn.execute(
                "INSERT INTO commission(product_id, name, description, category, price,"
                " commission_percent, seller_name, seller_phone, photo, status, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (product_id, str(data.get("name") or ""), str(data.get("description") or ""),
                 str(data.get("category") or "Комиссия"), int(float(data.get("price") or 0)),
                 percent, str(data.get("seller_name") or ""), str(data.get("seller_phone") or ""),
                 str(data.get("photo") or ""), str(data.get("status") or "active"), _now_iso()))
            self._conn.commit()
            r = self._q1("SELECT * FROM commission WHERE id=?", (cur.lastrowid,))
            return dict(r)

    def commission_request(self, data: dict) -> dict:
        """Заявка от владельца вещи (публичная форма «Сдать вещь на комиссию»)."""
        return self.add_commission({**data, "status": "request"}, create_product=False)

    def _mark_commission_sold(self, items: list, order_id: str):
        for it in items:
            rows = self._q("SELECT * FROM commission WHERE product_id=? AND status='active'",
                           (int(it["id"]),))
            for c in rows:
                self._conn.execute(
                    "UPDATE commission SET status='sold', sold_order_id=?, sold_at=?,"
                    " payout_amount=(price*(100-commission_percent))/100, payout_status='unpaid'"
                    " WHERE id=?", (order_id, _now_iso(), c["id"]))
                # снимаем товар с продажи
                self._conn.execute(
                    "UPDATE products SET in_stock=0, updated_at=? WHERE id=?",
                    (_now_iso(), int(c["product_id"])))

    def set_commission_payout(self, commission_id: int, status: str = "paid") -> dict:
        with _lock:
            r = self.get_commission(commission_id)
            if not r:
                return None
            self._conn.execute("UPDATE commission SET payout_status=? WHERE id=?",
                               (status, int(commission_id)))
            self._conn.commit()
            return self.get_commission(commission_id)

    def set_commission_status(self, commission_id: int, status: str) -> dict:
        """active | returned — при возврате товар снимается с продажи."""
        with _lock:
            r = self.get_commission(commission_id)
            if not r:
                return None
            self._conn.execute("UPDATE commission SET status=? WHERE id=?", (status, int(commission_id)))
            if r.get("product_id"):
                self.update_product(r["product_id"], {"in_stock": status == "active"})
            self._conn.commit()
            return self.get_commission(commission_id)

    def delete_commission(self, commission_id: int) -> bool:
        with _lock:
            r = self.get_commission(commission_id)
            if not r:
                return False
            if r.get("product_id"):
                self.update_product(r["product_id"], {"in_stock": False})
            self._conn.execute("DELETE FROM commission WHERE id=?", (int(commission_id),))
            self._conn.commit()
            return True

    def commission_stats(self) -> dict:
        rows = self.commission_items()
        active = sum(1 for r in rows if r["status"] == "active")
        sold = [r for r in rows if r["status"] == "sold"]
        requests = sum(1 for r in rows if r["status"] == "request")
        earned = sum(r["price"] - r["payout_amount"] for r in sold)
        to_pay = sum(r["payout_amount"] for r in sold if r["payout_status"] == "unpaid")
        return {"active": active, "sold": len(sold), "requests": requests,
                "earned": earned, "to_pay": to_pay}

    # ---------------- подписчики ----------------
    def subscribe(self, email: str) -> dict:
        import re
        email = (email or "").strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise ValueError("Некорректный email")
        with _lock:
            try:
                self._conn.execute("INSERT INTO subscribers(email, created_at) VALUES(?,?)",
                                   (email, _now_iso()))
                self._conn.commit()
                return {"ok": True, "new": True}
            except sqlite3.IntegrityError:
                return {"ok": True, "new": False}

    def subscribers_count(self) -> int:
        return self._count("SELECT COUNT(*) c FROM subscribers")

    # ---------------- маркетплейс: продавцы ----------------
    def marketplace_settings(self) -> dict:
        return self._settings.get("marketplace") or {}

    def _mp(self) -> dict:
        return self.marketplace_settings()

    def sellers(self, status: str = "") -> list:
        sql = "SELECT * FROM sellers"
        if status:
            sql += " WHERE status=?"
            return [dict(r) for r in self._q(sql + " ORDER BY id DESC", (status,))]
        return [dict(r) for r in self._q(sql + " ORDER BY id DESC")]

    def get_seller(self, seller_id=None, slug: str = "", key: str = "", tg_user_id: int = 0):
        if seller_id:
            r = self._q1("SELECT * FROM sellers WHERE id=?", (int(seller_id),))
        elif slug:
            r = self._q1("SELECT * FROM sellers WHERE slug=?", (slug,))
        elif key:
            r = self._q1("SELECT * FROM sellers WHERE key=?", (key,))
        elif tg_user_id:
            r = self._q1("SELECT * FROM sellers WHERE tg_user_id=?", (int(tg_user_id),))
        else:
            return None
        return dict(r) if r else None

    def register_seller(self, data: dict) -> dict:
        """Регистрация продавца. status: pending или active (если автоподтверждение)."""
        slug = str(data.get("slug") or "").strip() or ("s" + secrets.token_hex(4))
        store_name = str(data.get("store_name") or "").strip()
        if not store_name:
            raise ValueError("Укажите название магазина")
        mp = self._mp()
        status = "active" if mp.get("auto_approve_sellers") else "pending"
        default_plan = (self._settings.get("tariffs") or {}).get("seller_default_plan") or "start"
        with _lock:
            self._conn.execute(
                "INSERT INTO sellers(slug, store_name, description, tg_user_id, phone, email, key,"
                " status, commission_percent, balance, total_earned, plan, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (slug, store_name, str(data.get("description") or ""),
                 int(data.get("tg_user_id") or 0), str(data.get("phone") or ""),
                 str(data.get("email") or ""), secrets.token_hex(16), status,
                 int(data.get("commission_percent") or 0), 0, 0, default_plan,
                 _now_iso(), _now_iso()))
            self._conn.commit()
        return self.get_seller(slug=slug)

    def update_seller(self, seller_id: int, data: dict) -> dict:
        with _lock:
            s = self.get_seller(seller_id)
            if not s:
                return None
            for f in ("store_name", "description", "phone", "email"):
                if f in data and data[f] is not None:
                    s[f] = str(data[f]).strip()
            if "slug" in data and data["slug"]:
                s["slug"] = str(data["slug"]).strip()
            self._conn.execute(
                "UPDATE sellers SET slug=?, store_name=?, description=?, phone=?, email=?, updated_at=?"
                " WHERE id=?",
                (s["slug"], s["store_name"], s["description"], s["phone"], s["email"],
                 _now_iso(), int(seller_id)))
            self._conn.commit()
            return self.get_seller(seller_id)

    def set_seller_status(self, seller_id: int, status: str) -> dict:
        with _lock:
            self._conn.execute("UPDATE sellers SET status=?, updated_at=? WHERE id=?",
                               (status, _now_iso(), int(seller_id)))
            self._conn.execute(
                "UPDATE products SET in_stock=? WHERE seller_id=?",
                (1 if status == "active" else 0, int(seller_id)))
            self._conn.commit()
            return self.get_seller(seller_id)

    def set_seller_commission(self, seller_id: int, percent: int) -> dict:
        with _lock:
            self._conn.execute("UPDATE sellers SET commission_percent=?, updated_at=? WHERE id=?",
                               (max(0, int(percent)), _now_iso(), int(seller_id)))
            self._conn.commit()
            return self.get_seller(seller_id)

    def reset_seller_key(self, seller_id: int) -> str:
        with _lock:
            key = secrets.token_hex(16)
            self._conn.execute("UPDATE sellers SET key=?, updated_at=? WHERE id=?",
                               (key, _now_iso(), int(seller_id)))
            self._conn.commit()
            return key

    def _accrue_seller(self, seller_id: int, amount: int):
        if not amount:
            return
        self._conn.execute(
            "UPDATE sellers SET balance=MAX(0, balance+?), total_earned=MAX(0, total_earned+?),"
            " updated_at=? WHERE id=?",
            (int(amount), int(amount), _now_iso(), int(seller_id)))
        self._conn.commit()

    def seller_products(self, seller_id: int) -> list:
        return [p for p in self.products() if int(p.get("seller_id") or 0) == int(seller_id)]

    def seller_orders(self, seller_id: int) -> list:
        out = []
        for o in self.orders(limit=2000):
            for it in o["items"]:
                if int(it.get("seller_id") or 0) == int(seller_id):
                    out.append(o)
                    break
        return out

    def seller_stats(self, seller_id: int) -> dict:
        s = self.get_seller(seller_id) or {}
        orders = self.seller_orders(seller_id)
        paid = {"paid", "processing", "shipped", "delivered", "completed"}
        sales = sum(sum(i["price"] * i["qty"] for i in o["items"]
                        if int(i.get("seller_id") or 0) == int(seller_id))
                    for o in orders if o["status"] in paid)
        return {
            "products": len(self.seller_products(seller_id)),
            "orders": len(orders),
            "sales": sales,
            "balance": int(s.get("balance") or 0),
            "total_earned": int(s.get("total_earned") or 0),
        }

    # ---------------- рейтинг продавца (AUDIT.md #7) ----------------
    def seller_rating(self, seller_id: int) -> dict:
        s = self.get_seller(seller_id)
        if not s:
            return {"rating": 0, "reviews_approved": 0, "reviews_total": 0,
                    "avg_rating": 0, "approval_rate": 100, "response_rate": 0,
                    "response_time_hours": 24, "seller_name": "—", "verified": False,
                    "status": "pending", "plan": "start"}
        products = self.seller_products(seller_id)
        review_rows = []
        for p in products:
            review_rows.extend(self.reviews(p["id"], only_approved=False))
        total_reviews = len(review_rows)
        approved_reviews = sum(1 for r in review_rows if r.get("status") == "approved")
        approved_ratings = [r["rating"] for r in review_rows if r.get("status") == "approved"]
        avg_rating = round(sum(approved_ratings) / len(approved_ratings), 1) if approved_ratings else 0
        approval_rate = round(approved_reviews / max(total_reviews, 1) * 100, 1) if total_reviews > 0 else 100
        chat_threads = self.chat_threads_seller(seller_id)
        response_rate = 100 if chat_threads else 0
        response_time_hours = 2 if s.get("status") == "active" else 24
        verified_badge = s.get("verification_status") == "verified"
        final_score = min(5.0, (avg_rating * 0.6) + (approval_rate / 20) + (response_rate / 20))
        return {
            "rating": round(final_score, 1),
            "reviews_approved": approved_reviews,
            "reviews_total": total_reviews,
            "avg_rating": avg_rating,
            "approval_rate": approval_rate,
            "response_rate": response_rate,
            "response_time_hours": response_time_hours,
            "seller_name": s.get("store_name", ""),
            "verified": verified_badge,
            "status": s.get("status", "pending"),
            "plan": s.get("plan", "start"),
            "commission_percent": int(s.get("commission_percent") or 0),
        }

    def seller_rating_details(self, seller_id: int) -> dict:
        s = self.get_seller(seller_id) or {}
        products = self.seller_products(seller_id)
        ratings_per_product = []
        for p in products:
            revs = self.reviews(p["id"], only_approved=True)
            if revs:
                ratings_per_product.append({
                    "product_id": p["id"],
                    "product_name": p.get("name", ""),
                    "avg": round(sum(r["rating"] for r in revs) / len(revs), 1),
                    "count": len(revs),
                })
        overall = self.seller_rating(seller_id)
        seller_reviews = []
        for p in products:
            for r in self.reviews(p["id"], only_approved=True):
                seller_reviews.append({
                    "author": r.get("author", "Гость"),
                    "rating": r.get("rating", 5),
                    "text": r.get("text", ""),
                    "product_name": p.get("name", ""),
                    "date": r.get("created_at", ""),
                })
        return {
            "seller": s,
            "rating_summary": overall,
            "product_ratings": sorted(ratings_per_product, key=lambda x: -x["avg"]),
            "reviews_list": sorted(seller_reviews, key=lambda x: x.get("date", ""), reverse=True)[:50],
        }

    # ---------------- отзывы о продавце (#7 улучшение) ----------------
    def add_seller_review(self, seller_id: int, buyer_key: str, buyer_name: str = "",
                          rating: int = 5, text: str = "") -> dict:
        s = self.get_seller(seller_id)
        if not s:
            raise ValueError("Продавец не найден")
        if int(s.get("id") or 0) != int(seller_id):
            raise ValueError("Неверный ID продавца")
        with _lock:
            status = "approved" if self._settings.get("auto_approve_reviews") else "pending"
            self._conn.execute(
                "INSERT INTO seller_reviews(seller_id, buyer_key, buyer_name, rating, text, status, created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (int(seller_id), str(buyer_key or ""), str(buyer_name or "")[:60],
                 max(1, min(5, int(rating))), str(text or "")[:1000], status, _now_iso()))
            self._conn.commit()
            r = self._q1("SELECT * FROM seller_reviews ORDER BY id DESC LIMIT 1")
            return dict(r) if r else None

    def seller_reviews(self, seller_id: int, only_approved: bool = True) -> list:
        sql = "SELECT * FROM seller_reviews WHERE seller_id=?"
        if only_approved:
            sql += " AND status='approved'"
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in self._q(sql, (int(seller_id),))]

    def seller_review_stats(self, seller_id: int) -> dict:
        rows = self._q("SELECT rating FROM seller_reviews WHERE seller_id=? AND status='approved'", (int(seller_id),))
        if not rows:
            return {"avg": 0, "count": 0}
        vals = [r["rating"] for r in rows]
        return {"avg": round(sum(vals) / len(vals), 1), "count": len(vals)}

    def create_payout(self, seller_id: int, amount: int, status: str = "paid", note: str = "") -> dict:
        with _lock:
            s = self.get_seller(seller_id)
            if not s:
                raise ValueError("Продавец не найден")
            amount = int(amount)
            if amount <= 0:
                raise ValueError("Сумма должна быть больше нуля")
            if amount > int(s["balance"]):
                raise ValueError("Сумма превышает баланс продавца")
            self._conn.execute(
                "INSERT INTO payouts(seller_id, amount, status, note, created_at) VALUES(?,?,?,?,?)",
                (int(seller_id), amount, status, str(note or ""), _now_iso()))
            self._accrue_seller(seller_id, -amount)
            self._conn.commit()
            r = self._q1("SELECT * FROM payouts ORDER BY id DESC LIMIT 1")
            return dict(r)

    def payouts(self, seller_id: int = 0) -> list:
        sql = "SELECT * FROM payouts"
        if seller_id:
            sql += " WHERE seller_id=?"
            return [dict(r) for r in self._q(sql + " ORDER BY id DESC", (int(seller_id),))]
        return [dict(r) for r in self._q(sql + " ORDER BY id DESC")]

    def seller_promos(self, seller_id: int) -> list:
        return [p for p in self.promos() if int(p.get("seller_id") or 0) == int(seller_id)]

    def seller_public(self, slug: str) -> dict:
        s = self.get_seller(slug=slug)
        if not s:
            return None
        return {
            "id": s["id"], "slug": s["slug"], "store_name": s["store_name"],
            "description": s["description"], "status": s["status"],
            "created_at": s["created_at"],
            "products": [p for p in self.seller_products(s["id"]) if p.get("in_stock")],
        }

    def mark_payout_status(self, payout_id: int, status: str) -> dict:
        """Админ подтверждает запрошенную выплату (requested -> paid)."""
        with _lock:
            self._conn.execute("UPDATE payouts SET status=? WHERE id=?", (status, int(payout_id)))
            self._conn.commit()
            r = self._q1("SELECT * FROM payouts WHERE id=?", (int(payout_id),))
            return dict(r) if r else None

    def commission_report(self, date_from: str = "", date_to: str = "") -> dict:
        """Отчёт по комиссиям за период: продажи, комиссия площадки, выплаты."""
        paid = {"paid", "processing", "shipped", "delivered"}
        from_d = (date_from or "")[:10]
        to_d = (date_to or "")[:10]
        rows = {}
        for o in self.orders(limit=5000):
            if o["status"] not in paid:
                continue
            d = (o.get("created_at") or "")[:10]
            if from_d and d < from_d:
                continue
            if to_d and d > to_d:
                continue
            for it in o["items"]:
                sid = int(it.get("seller_id") or 0)
                if not sid:
                    continue
                r = rows.setdefault(sid, {"sales": 0, "commission": 0, "net": 0, "orders": set()})
                r["sales"] += int(it["price"]) * int(it["qty"])
                r["commission"] += int(it.get("commission_amount") or 0)
                r["net"] += int(it.get("seller_net") or 0)
                r["orders"].add(o["id"])
        out = []
        for sid, r in rows.items():
            s = self.get_seller(sid)
            out.append({
                "seller_id": sid,
                "store_name": (s or {}).get("store_name", "?"),
                "orders": len(r["orders"]),
                "sales": r["sales"],
                "commission": r["commission"],
                "net": r["net"],
            })
        payouts_total = 0
        for p in self.payouts():
            pd = (p.get("created_at") or "")[:10]
            if from_d and pd < from_d:
                continue
            if to_d and pd > to_d:
                continue
            payouts_total += int(p["amount"])
        out = sorted(out, key=lambda x: -x["sales"])
        return {
            "rows": out,
            "totals": {
                "sales": sum(x["sales"] for x in out),
                "commission": sum(x["commission"] for x in out),
                "net": sum(x["net"] for x in out),
                "payouts": payouts_total,
            },
        }

    # ---------------- склад: пользователи и журнал ----------------
    def wh_add_user(self, login: str, name: str, password: str, role: str = "worker") -> dict:
        import hashlib
        login = str(login).strip().lower()
        if not login or not password:
            raise ValueError("Укажите логин и пароль")
        if role not in ("admin", "worker"):
            raise ValueError("Роль: admin или worker")
        with _lock:
            self._conn.execute(
                "INSERT INTO wh_users(login, pass_hash, name, role, created_at) VALUES(?,?,?,?,?)",
                (login, hashlib.sha256(password.encode()).hexdigest(), str(name or login), role, _now_iso()))
            self._conn.commit()
        return self.wh_users()
    def wh_update_user(self, uid: int, data: dict) -> dict:
        import hashlib
        with _lock:
            u = self._q1("SELECT * FROM wh_users WHERE id=?", (int(uid),))
            if not u:
                raise ValueError("Пользователь не найден")
            name = str(data.get("name", u["name"]))
            role = str(data.get("role", u["role"]))
            if role not in ("admin", "worker"):
                raise ValueError("Роль: admin или worker")
            if data.get("password"):
                self._conn.execute("UPDATE wh_users SET pass_hash=?, name=?, role=? WHERE id=?",
                                   (hashlib.sha256(str(data["password"]).encode()).hexdigest(), name, role, int(uid)))
            else:
                self._conn.execute("UPDATE wh_users SET name=?, role=? WHERE id=?",
                                   (name, role, int(uid)))
            self._conn.commit()
        return self.wh_users()
    def wh_delete_user(self, uid: int) -> bool:
        with _lock:
            self._conn.execute("DELETE FROM wh_users WHERE id=?", (int(uid),))
            self._conn.commit()
            return self._conn.total_changes > 0
    def wh_users(self) -> list:
        return [dict(r) for r in self._q("SELECT id, login, name, role, created_at FROM wh_users ORDER BY id")]
    def wh_user_by_login(self, login: str):
        r = self._q1("SELECT * FROM wh_users WHERE login=?", (str(login).strip().lower(),))
        return dict(r) if r else None

    def wh_check(self, login: str, password: str):
        import hashlib
        r = self._q1("SELECT * FROM wh_users WHERE login=?", (str(login).strip().lower(),))
        if not r:
            return None
        if r["pass_hash"] != hashlib.sha256(str(password).encode()).hexdigest():
            return None
        return dict(r)
    def wh_change_password(self, login: str, old_password: str, new_password: str) -> bool:
        import hashlib
        u = self.wh_check(login, old_password)
        if not u:
            return False
        with _lock:
            self._conn.execute("UPDATE wh_users SET pass_hash=? WHERE id=?",
                               (hashlib.sha256(str(new_password).encode()).hexdigest(), int(u["id"])))
            self._conn.commit()
        return True

    def wh_log_add(self, user_name: str, action: str, details: str = ""):
        with _lock:
            self._conn.execute("INSERT INTO wh_log(ts, user_name, action, details) VALUES(?,?,?,?)",
                               (_now_iso(), str(user_name), str(action), str(details)[:500]))
            self._conn.commit()
    def wh_logs(self, limit: int = 100) -> list:
        return [dict(r) for r in self._q("SELECT * FROM wh_log ORDER BY id DESC LIMIT ?", (limit,))]

    def set_cloud_state(self, state: dict):
        """Состояние синхронизации с облаком: маппинг фото local->URL, время."""
        with _lock:
            self._settings["cloud_state"] = state
            self._save_settings_to_db()

    def export_sqlite_backup(self, dest_path: str) -> str:
        """Снимок живой SQLite-базы в отдельный файл для безопасной выгрузки в облако."""
        dest_path = os.path.abspath(dest_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with _lock:
            dst = sqlite3.connect(dest_path)
            try:
                self._conn.backup(dst)
            finally:
                dst.close()
        return dest_path

    def wh_scan_add(self, user_name: str, mode: str, code: str, product_id: int,
                    qty: int, result: str):
        with _lock:
            self._conn.execute(
                "INSERT INTO wh_scans(ts, user_name, mode, code, product_id, qty, result)"
                " VALUES(?,?,?,?,?,?,?)",
                (_now_iso(), str(user_name), str(mode), str(code), int(product_id), int(qty), str(result)))
            self._conn.commit()

    def wh_scans(self, limit: int = 50) -> list:
        return [dict(r) for r in self._q("SELECT * FROM wh_scans ORDER BY id DESC LIMIT ?", (limit,))]

    def duplicate_product(self, product_id: int) -> dict:
        """Копия товара (SKU получает суффикс -2, -3, …). Из ТЗ: P-4 «Создать копию»."""
        with _lock:
            p = self.get_product(product_id)
            if not p:
                return None
            base = str(p.get("code") or f"TG-{p['id']}")
            i = 2
            while True:
                new_code = f"{base}-{i}"
                if not self._q1("SELECT 1 FROM products WHERE code=?", (new_code,)):
                    break
                i += 1
            copy = {k: p[k] for k in ("name", "category", "price", "old_price", "stock",
                                       "description", "photo", "photos", "barcode",
                                       "storage_location", "owner_name", "on_showcase",
                                       "purchase_price", "seller_id")}
            copy.update({"id": self.next_product_id(), "code": new_code,
                         "badges": list(p.get("badges") or []), "in_stock": bool(p.get("in_stock")),
                         "is_archived": 0})
            self._insert_product(copy)
            self._conn.commit()
            return dict(copy)

    # --- отложенные публикации (ТЗ: SM-3, SM-4) ---
    def add_scheduled_post(self, product_id: int, platform: str, scheduled_at: str,
                           created_by: str = "") -> dict:
        with _lock:
            self._conn.execute(
                "INSERT INTO social_posts(product_id, platform, content, status, scheduled_at,"
                " created_by) VALUES(?,?,?,?,?,?)",
                (int(product_id), str(platform), "", "scheduled", str(scheduled_at), str(created_by)))
            self._conn.commit()
            r = self._q1("SELECT * FROM social_posts ORDER BY id DESC LIMIT 1")
            return dict(r)

    def scheduled_posts(self) -> list:
        return [dict(r) for r in self._q(
            "SELECT * FROM social_posts WHERE status IN ('scheduled','draft') ORDER BY scheduled_at")]

    def all_social_posts(self, limit: int = 100) -> list:
        return [dict(r) for r in self._q(
            "SELECT * FROM social_posts ORDER BY id DESC LIMIT ?", (limit,))]

    def set_post_status(self, post_id: int, status: str, error: str = "", published_at: str = ""):
        with _lock:
            self._conn.execute(
                "UPDATE social_posts SET status=?, error=?, published_at=? WHERE id=?",
                (status, str(error)[:300], published_at or (_now_iso() if status == "published" else ""),
                 int(post_id)))
            self._conn.commit()

    def delete_scheduled_post(self, post_id: int) -> bool:
        with _lock:
            self._conn.execute("DELETE FROM social_posts WHERE id=?", (int(post_id),))
            self._conn.commit()
            return self._conn.total_changes > 0

    def due_scheduled_posts(self) -> list:
        now = _now_iso()
        return [dict(r) for r in self._q(
            "SELECT * FROM social_posts WHERE status='scheduled' AND scheduled_at<=? ORDER BY scheduled_at",
            (now,))]

    # ---------------- рекомендации ----------------
    def _sold_qty(self) -> dict:
        sold = {}
        for o in self.orders(limit=5000):
            if o["status"] in ("cancelled", "pending_payment"):
                continue
            for i in o["items"]:
                sold[int(i["id"])] = sold.get(int(i["id"]), 0) + i["qty"]
        return sold

    def top_sellers(self, limit: int = 8) -> list:
        sold = self._sold_qty()
        ids = sorted(sold, key=sold.get, reverse=True)[:limit]
        return [p for pid in ids if (p := self.get_product(pid)) and p["in_stock"]]

    def related_products(self, product_id: int, limit: int = 8) -> dict:
        """Рекомендации: из той же категории, вместе покупают, лидеры продаж."""
        p = self.get_product(product_id)
        if not p:
            return {"same_category": [], "co_bought": [], "top": []}
        same_cat = [x for x in self.products()
                    if x["id"] != p["id"] and x.get("category") == p.get("category") and x["in_stock"]][:limit]
        co = {}
        for o in self.orders(limit=5000):
            if o["status"] in ("cancelled", "pending_payment"):
                continue
            ids = {int(i["id"]) for i in o["items"]}
            if p["id"] in ids:
                for other in ids - {p["id"]}:
                    co[other] = co.get(other, 0) + 1
        co_ids = [pid for pid, _ in sorted(co.items(), key=lambda x: -x[1]) if pid != p["id"]]
        co_bought = [x for pid in co_ids if (x := self.get_product(pid)) and x["in_stock"]][:limit]
        top = [x for x in self.top_sellers(limit * 2)
               if x["id"] != p["id"] and x.get("category") != p.get("category")][:limit]
        return {"same_category": same_cat, "co_bought": co_bought, "top": top}

    # ---------------- тарифы (настраиваются администратором) ----------------
    def _tariffs(self) -> dict:
        return self._settings.get("tariffs") or {}

    def tariff_commission(self, seller: dict) -> int:
        """Комиссия площадки для продавца. Приоритет: индивидуальная настройка → тариф → база."""
        individual = int(seller.get("commission_percent") or 0)
        if individual > 0:
            return individual
        t = self._tariffs()
        if not t.get("enabled"):
            return int(self._settings.get("marketplace", {}).get("commission_percent") or 15)
        base = int(t.get("commission_percent") or 15)
        disc = int(self.seller_plan(seller).get("commission_discount") or 0)
        return max(0, base - disc)

    def seller_plan(self, seller: dict) -> dict:
        """План продавца из настроек тарифов (или план по умолчанию)."""
        t = self._tariffs()
        plans = list(t.get("seller_plans") or [])
        if not plans:
            return {}
        pid = seller.get("plan") or t.get("seller_default_plan") or "start"
        return next((p for p in plans if p.get("id") == pid), plans[0])

    def set_seller_plan(self, seller_id: int, plan_id: str) -> dict:
        t = self._tariffs()
        ids = {p.get("id") for p in (t.get("seller_plans") or [])}
        if plan_id not in ids:
            raise ValueError("Неизвестный тариф")
        with _lock:
            self._conn.execute("UPDATE sellers SET plan=?, updated_at=? WHERE id=?",
                               (plan_id, _now_iso(), int(seller_id)))
            self._conn.commit()
            return self.get_seller(seller_id)

    def _month_key(self) -> str:
        return time.strftime("%Y-%m")

    def seller_ai_used(self, seller_id: int) -> int:
        s = self.get_seller(seller_id) or {}
        if s.get("ai_month") != self._month_key():
            return 0
        return int(s.get("ai_used") or 0)

    def spend_seller_ai(self, seller_id: int) -> int:
        """Регистрирует использование ИИ. Возвращает сколько осталось (-1 = без лимита, 0 = исчерпан)."""
        t = self._tariffs()
        s = self.get_seller(seller_id)
        if not s:
            return -1
        limit = int(self.seller_plan(s).get("ai_month") or 0) if t.get("enabled") else -1
        if t.get("enabled") and limit == 0:
            return 0
        with _lock:
            used = self.seller_ai_used(seller_id)
            if limit >= 0:
                if used >= limit:
                    return 0
                self._conn.execute(
                    "UPDATE sellers SET ai_used=?, ai_month=?, updated_at=? WHERE id=?",
                    (used + 1, self._month_key(), _now_iso(), int(seller_id)))
            else:
                self._conn.execute(
                    "UPDATE sellers SET ai_used=ai_used+1, ai_month=?, updated_at=? WHERE id=?",
                    (self._month_key(), _now_iso(), int(seller_id)))
            self._conn.commit()
            return (limit - used - 1) if limit >= 0 else -1

    def seller_limits(self, seller: dict) -> dict:
        """Лимиты и использование по тарифу продавца."""
        t = self._tariffs()
        plan = self.seller_plan(seller)
        used_ai = self.seller_ai_used(int(seller.get("id") or 0))
        ai_limit = int(plan.get("ai_month") or 0)
        return {
            "tariffs_enabled": bool(t.get("enabled")),
            "plan": plan,
            "max_products": int(plan.get("max_products") or 0),
            "used_products": len(self.seller_products(int(seller.get("id") or 0))),
            "max_photos": int(plan.get("max_photos") or 10),
            "ai_month": ai_limit,
            "ai_used": used_ai,
            "ai_left": max(0, ai_limit - used_ai) if ai_limit >= 0 else -1,
            "boost_month": int(plan.get("boost_month") or 0),
            "vip_products": int(plan.get("vip_products") or 0),
            "promos_max": int(plan.get("promos_max") or 0),
            "commission": self.tariff_commission(seller),
            "escrow_days": int(t.get("escrow_days") or 0),
        }

    # ---------------- верификация продавцов ----------------
    def set_seller_verification(self, seller_id: int, status: str, data: dict = None) -> dict:
        with _lock:
            s = self.get_seller(seller_id)
            if not s:
                return None
            vd = {}
            try:
                vd = json.loads(s.get("verification_data") or "{}")
            except Exception:
                vd = {}
            if data:
                vd.update({k: v for k, v in data.items() if v is not None})
            self._conn.execute(
                "UPDATE sellers SET verification_status=?, verification_data=?, updated_at=? WHERE id=?",
                (status, json.dumps(vd, ensure_ascii=False), _now_iso(), int(seller_id)))
            self._conn.commit()
            return self.get_seller(seller_id)

    def seller_verification(self, seller: dict) -> dict:
        try:
            vd = json.loads(seller.get("verification_data") or "{}")
        except Exception:
            vd = {}
        return {"status": seller.get("verification_status") or "unverified", "data": vd}

    # ---------------- эскроу (холд средств продавца) ----------------
    def _accrue_seller_held(self, seller_id: int, amount: int):
        if not amount:
            return
        self._conn.execute(
            "UPDATE sellers SET held_balance=MAX(0, held_balance+?),"
            " total_earned=MAX(0, total_earned+?), updated_at=? WHERE id=?",
            (int(amount), int(amount), _now_iso(), int(seller_id)))
        self._conn.commit()

    def release_seller_held(self, seller_id: int, amount: int) -> int:
        """Переводит сумму из холда в доступный баланс. Возвращает сколько переведено."""
        with _lock:
            s = self.get_seller(seller_id)
            if not s:
                return 0
            amount = max(0, int(amount))
            release = min(amount, int(s.get("held_balance") or 0))
            if release <= 0:
                return 0
            self._conn.execute(
                "UPDATE sellers SET held_balance=held_balance-?, balance=balance+?, updated_at=? WHERE id=?",
                (release, release, _now_iso(), int(seller_id)))
            self._conn.commit()
            return release

    def release_all_held(self, seller_id: int) -> int:
        s = self.get_seller(seller_id)
        if not s:
            return 0
        return self.release_seller_held(seller_id, int(s.get("held_balance") or 0))

    def _release_order_held(self, o: dict):
        """Размораживает средства продавцов по оплаченному заказу."""
        if not o.get("sellers_accrued") or o.get("sellers_released"):
            return
        for it in o.get("items", []):
            if it.get("seller_id") and it.get("seller_net"):
                self.release_seller_held(int(it["seller_id"]), int(it["seller_net"]))
        o["sellers_released"] = True

    def auto_release_held(self) -> int:
        """Автоматически размораживает холд по заказам старше escrow_days. Возвращает число заказов."""
        t = self._tariffs()
        if not t.get("enabled"):
            return 0
        days = int(t.get("escrow_days") or 0)
        if days <= 0:
            return 0
        cutoff = time.time() - days * 86400
        released = 0
        with _lock:
            for o in self.orders(limit=5000):
                if o.get("sellers_accrued") and not o.get("sellers_released") \
                        and o["status"] in ("paid", "processing", "shipped"):
                    paid_at = (o.get("payment") or {}).get("paid_at") or o.get("created_at") or ""
                    try:
                        ts = time.mktime(time.strptime(paid_at[:19], "%Y-%m-%dT%H:%M:%S"))
                    except Exception:
                        ts = 0
                    if 0 < ts < cutoff:
                        self._release_order_held(o)
                        o["history"].append({"status": "held_released", "at": _now_iso()})
                        self._update_order(o)
                        released += 1
            if released:
                self._conn.commit()
        return released

    # ---------------- чат покупатель <-> продавец ----------------
    def chat_add(self, product_id: int, seller_id: int, buyer_key: str, buyer_name: str,
                 sender: str, text: str) -> dict:
        with _lock:
            self._conn.execute(
                "INSERT INTO chat_messages(product_id, seller_id, buyer_key, buyer_name, sender, text, ts,"
                " read_buyer, read_seller) VALUES(?,?,?,?,?,?,?,?,?)",
                (int(product_id), int(seller_id), str(buyer_key or ""), str(buyer_name or ""),
                 str(sender), str(text), _now_iso(), 1 if sender == "buyer" else 0,
                 1 if sender == "seller" else 0))
            self._conn.commit()
            r = self._q1("SELECT * FROM chat_messages ORDER BY id DESC LIMIT 1")
            return dict(r) if r else None

    def chat_messages(self, product_id: int, seller_id: int, buyer_key: str) -> list:
        return [dict(r) for r in self._q(
            "SELECT * FROM chat_messages WHERE product_id=? AND seller_id=? AND buyer_key=? ORDER BY id ASC",
            (int(product_id), int(seller_id), str(buyer_key or "")))]

    def chat_threads_buyer(self, buyer_key: str) -> list:
        """Список диалогов покупателя (по продавцу+товару), с непрочитанными."""
        rows = self._q(
            "SELECT product_id, seller_id, MAX(id) mid, "
            "SUM(CASE WHEN sender='seller' AND read_buyer=0 THEN 1 ELSE 0 END) unread "
            "FROM chat_messages WHERE buyer_key=? GROUP BY product_id, seller_id ORDER BY mid DESC",
            (str(buyer_key or ""),))
        out = []
        for r in rows:
            last_row = self._q1("SELECT * FROM chat_messages WHERE id=?", (r["mid"],))
            last = dict(last_row) if last_row else {}
            seller = self.get_seller(int(r["seller_id"])) or {}
            product = self.get_product(int(r["product_id"])) or {}
            out.append({
                "product_id": r["product_id"], "seller_id": r["seller_id"],
                "product_name": product.get("name", ""), "product_photo": product.get("photo", ""),
                "seller_name": seller.get("store_name", ""), "seller_slug": seller.get("slug", ""),
                "unread": int(r["unread"] or 0), "last_text": (last or {}).get("text", ""),
                "last_ts": (last or {}).get("ts", ""), "last_sender": (last or {}).get("sender", ""),
            })
        return out

    def chat_threads_seller(self, seller_id: int) -> list:
        rows = self._q(
            "SELECT product_id, buyer_key, MAX(id) mid, "
            "SUM(CASE WHEN sender='buyer' AND read_seller=0 THEN 1 ELSE 0 END) unread "
            "FROM chat_messages WHERE seller_id=? GROUP BY product_id, buyer_key ORDER BY mid DESC",
            (int(seller_id),))
        out = []
        for r in rows:
            last_row = self._q1("SELECT * FROM chat_messages WHERE id=?", (r["mid"],))
            last = dict(last_row) if last_row else {}
            product = self.get_product(int(r["product_id"])) or {}
            first_buyer = self._q1(
                "SELECT buyer_name FROM chat_messages WHERE seller_id=? AND product_id=? AND buyer_key=?"
                " AND sender='buyer' ORDER BY id ASC LIMIT 1",
                (int(seller_id), int(r["product_id"]), str(r["buyer_key"])))
            buyer_name = (dict(first_buyer) or {}).get("buyer_name", "") if first_buyer else ""
            out.append({
                "product_id": r["product_id"], "buyer_key": r["buyer_key"],
                "product_name": product.get("name", ""), "product_photo": product.get("photo", ""),
                "buyer_name": buyer_name,
                "unread": int(r["unread"] or 0), "last_text": (last or {}).get("text", ""),
                "last_ts": (last or {}).get("ts", ""), "last_sender": (last or {}).get("sender", ""),
            })
        return out

    def chat_mark_read(self, side: str, product_id: int, seller_id: int, buyer_key: str):
        with _lock:
            col = "read_buyer" if side == "buyer" else "read_seller"
            self._conn.execute(
                f"UPDATE chat_messages SET {col}=1 WHERE product_id=? AND seller_id=? AND buyer_key=? AND {col}=0",
                (int(product_id), int(seller_id), str(buyer_key or "")))
            self._conn.commit()

    def chat_unread_buyer(self, buyer_key: str) -> int:
        r = self._q1("SELECT COUNT(*) c FROM chat_messages WHERE buyer_key=? AND sender='seller' AND read_buyer=0",
                     (str(buyer_key or ""),))
        return int(r["c"]) if r else 0

    def chat_unread_seller(self, seller_id: int) -> int:
        r = self._q1("SELECT COUNT(*) c FROM chat_messages WHERE seller_id=? AND sender='buyer' AND read_seller=0",
                     (int(seller_id),))
        return int(r["c"]) if r else 0

    # ---------------- торг / предложение цены (#9) ----------------
    def create_offer(self, product_id: int, buyer_key: str, buyer_name: str = "",
                     proposed_price: int = 0, message: str = "") -> dict:
        product = self.get_product(product_id)
        if not product:
            raise ValueError("Товар не найден")
        seller_id = int(product.get("seller_id") or 0)
        proposed_price = max(1, int(proposed_price or 0))
        with _lock:
            self._conn.execute(
                "INSERT INTO offers(product_id, seller_id, buyer_key, buyer_name, proposed_price, message, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (int(product_id), seller_id, str(buyer_key or ""), str(buyer_name or ""),
                 proposed_price, str(message or ""), "pending", _now_iso(), _now_iso()))
            self._conn.commit()
            r = self._q1("SELECT * FROM offers ORDER BY id DESC LIMIT 1")
            return dict(r)

    def get_offers(self, seller_id: int = 0, buyer_key: str = "", product_id: int = 0, status: str = "") -> list:
        sql = "SELECT * FROM offers WHERE 1=1"
        args = []
        if seller_id:
            sql += " AND seller_id=?"
            args.append(int(seller_id))
        if buyer_key:
            sql += " AND buyer_key=?"
            args.append(str(buyer_key))
        if product_id:
            sql += " AND product_id=?"
            args.append(int(product_id))
        if status:
            sql += " AND status=?"
            args.append(str(status))
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in self._q(sql, tuple(args))]

    def offer_by_id(self, offer_id: int) -> dict:
        r = self._q1("SELECT * FROM offers WHERE id=?", (int(offer_id),))
        return dict(r) if r else None

    def respond_to_offer(self, offer_id: int, status: str, seller_response_price: int = 0, seller_note: str = "") -> dict:
        allowed = {"accepted", "rejected", "countered", "cancelled"}
        status = str(status or "").lower()
        if status not in allowed:
            raise ValueError("Недопустимый статус ответа: " + status)
        with _lock:
            r = self.offer_by_id(offer_id)
            if not r:
                raise ValueError("Предложение не найдено")
            self._conn.execute(
                "UPDATE offers SET status=?, seller_response_price=?, seller_note=?, updated_at=? WHERE id=?",
                (status, int(seller_response_price or 0), str(seller_note or ""), _now_iso(), int(offer_id)))
            self._conn.commit()
            return self.offer_by_id(offer_id)

    def cancel_offer(self, offer_id: int, buyer_key: str) -> dict:
        with _lock:
            r = self.offer_by_id(offer_id)
            if not r:
                raise ValueError("Предложение не найдено")
            if str(r.get("buyer_key") or "") != str(buyer_key or ""):
                raise ValueError("Нет прав на отмену")
            self._conn.execute(
                "UPDATE offers SET status='cancelled', updated_at=? WHERE id=? AND status='pending'",
                (_now_iso(), int(offer_id)))
            self._conn.commit()
            return self.offer_by_id(offer_id)

    # ---------------- сравнение товаров (#8) ----------------
    def compare_add(self, user_key: str, product_id: int) -> list:
        product = self.get_product(int(product_id))
        if not product or not product.get("in_stock"):
            raise ValueError("Товар не найден или отсутствует")
        with _lock:
            r = self._q1("SELECT * FROM comparisons WHERE user_key=? ORDER BY created_at DESC LIMIT 1",
                         (str(user_key or ""),))
            ids = []
            if r:
                try:
                    ids = json.loads(r.get("product_ids") or "[]")
                except Exception:
                    ids = []
            if int(product_id) in ids:
                return [self.get_product(pid) for pid in ids if self.get_product(pid) and self.get_product(pid).get("in_stock")]
            ids.append(int(product_id))
            ids = ids[-10:]  # максимум 10 товаров в сравнении
            if r:
                self._conn.execute(
                    "UPDATE comparisons SET product_ids=?, updated_at=? WHERE id=?",
                    (json.dumps(ids, ensure_ascii=False), _now_iso(), int(r["id"])))
            else:
                self._conn.execute(
                    "INSERT INTO comparisons(user_key, product_ids, created_at) VALUES(?,?,?)",
                    (str(user_key or ""), json.dumps(ids, ensure_ascii=False), _now_iso()))
            self._conn.commit()
            return [self.get_product(pid) for pid in ids if self.get_product(pid) and self.get_product(pid).get("in_stock")]

    def compare_remove(self, user_key: str, product_id: int) -> list:
        with _lock:
            r = self._q1("SELECT * FROM comparisons WHERE user_key=? ORDER BY created_at DESC LIMIT 1",
                         (str(user_key or ""),))
            if not r:
                return []
            try:
                ids = json.loads(r.get("product_ids") or "[]")
            except Exception:
                ids = []
            ids = [pid for pid in ids if int(pid) != int(product_id)]
            self._conn.execute(
                "UPDATE comparisons SET product_ids=?, updated_at=? WHERE id=?",
                (json.dumps(ids, ensure_ascii=False), _now_iso(), int(r["id"])))
            self._conn.commit()
            return [self.get_product(pid) for pid in ids if self.get_product(pid) and self.get_product(pid).get("in_stock")]

    def compare_list(self, user_key: str) -> list:
        r = self._q1("SELECT * FROM comparisons WHERE user_key=? ORDER BY created_at DESC LIMIT 1",
                     (str(user_key or ""),))
        if not r:
            return []
        try:
            ids = json.loads(r.get("product_ids") or "[]")
        except Exception:
            return []
        out = []
        for pid in ids:
            p = self.get_product(int(pid))
            if p and p.get("in_stock"):
                out.append(p)
        return out

    # ---------------- сохранённые поиски (#8) ----------------
    def saved_search_create(self, user_key: str, query: str = "", filters: dict = None) -> dict:
        filters_json = json.dumps(filters or {}, ensure_ascii=False)
        with _lock:
            self._conn.execute(
                "INSERT INTO saved_searches(user_key, query, filters, created_at, updated_at) VALUES(?,?,?,?,?)",
                (str(user_key or ""), str(query or "")[:200], filters_json, _now_iso(), _now_iso()))
            self._conn.commit()
            r = self._q1("SELECT * FROM saved_searches ORDER BY id DESC LIMIT 1")
            return dict(r) if r else None

    def saved_searches(self, user_key: str) -> list:
        return [dict(r) for r in self._q(
            "SELECT * FROM saved_searches WHERE user_key=? ORDER BY created_at DESC",
            (str(user_key or ""),))]

    def saved_search_delete(self, search_id: int, user_key: str) -> bool:
        with _lock:
            self._conn.execute(
                "DELETE FROM saved_searches WHERE id=? AND user_key=?",
                (int(search_id), str(user_key or "")))
            self._conn.commit()
            return self._conn.total_changes > 0

    # ---------------- уведомления по сохранённым поискам (#8 улучшение) ----------------
    def saved_search_notifications(self, user_key: str) -> list:
        """Проверяет сохранённые поиски пользователя и возвращает товары,
        добавленные после создания поиска (простая заглушка-реализация)."""
        searches = self.saved_searches(user_key)
        out = []
        for s in searches:
            try:
                filters = json.loads(s.get("filters") or "{}")
            except Exception:
                filters = {}
            query = s.get("query") or ""
            created_at = s.get("created_at") or ""
            products = self.products()
            matched = []
            for p in products:
                # Заглушка: считаем «новыми» товары, созданные после сохранения поиска,
                # и соответствующие фильтру категории и текстовому запросу.
                product_created = p.get("created_at") or ""
                if created_at and product_created and product_created > created_at:
                    if filters.get("category") and p.get("category") != filters["category"]:
                        continue
                    score = search_score(p, query) if query else 5
                    if query and score == 0:
                        continue
                    matched.append(p)
            if matched:
                out.append({
                    "search_id": s.get("id"),
                    "query": query,
                    "filters": filters,
                    "new_items": matched,
                    "new_count": len(matched),
                })
        return out

    # ---------------- монетизация: буст + VIP (#3 Этап) ----------------
    def create_boost(self, product_id: int, seller_id: int, duration_days: int = 1,
                     price: int = 0) -> dict:
        with _lock:
            p = self.get_product(product_id)
            if not p or not p.get("in_stock"):
                raise ValueError("Товар не найден или отсутствует")
            if int(p.get("seller_id") or 0) != int(seller_id):
                raise ValueError("Это не ваш товар")
            expires = datetime.now(timezone.utc) + timedelta(days=int(duration_days))
            self._conn.execute(
                "INSERT INTO boosts(product_id, seller_id, duration_days, started_at, expires_at, price, status)"
                " VALUES(?,?,?,?,?,?,?)",
                (int(product_id), int(seller_id), int(duration_days), _now_iso(),
                 expires.isoformat(), int(price or 0), "active"))
            self._conn.commit()
            r = self._q1("SELECT * FROM boosts ORDER BY id DESC LIMIT 1")
            return dict(r) if r else None

    def get_boosted_products(self) -> list:
        now = _now_iso()
        rows = self._q("SELECT * FROM boosts WHERE status='active' AND expires_at > ?", (now,))
        out = []
        for b in rows:
            p = self.get_product(b.get("product_id"))
            if p and p.get("in_stock"):
                p["boost_expires"] = b.get("expires_at")
                out.append(p)
        return out

    def active_boost_for_product(self, product_id: int) -> dict:
        now = _now_iso()
        r = self._q1("SELECT * FROM boosts WHERE product_id=? AND status='active' AND expires_at > ? ORDER BY expires_at DESC",
                     (int(product_id), now))
        return dict(r) if r else None

    def cancel_boost(self, boost_id: int) -> bool:
        with _lock:
            self._conn.execute("UPDATE boosts SET status='cancelled' WHERE id=?", (int(boost_id),))
            self._conn.commit()
            return self._conn.total_changes > 0

    def add_partner_referral(self, seller_id: int, referrer_seller_id: int,
                             buyer_key: str, order_id: str = "",
                             commission_amount: int = 0) -> dict:
        with _lock:
            self._conn.execute(
                "INSERT INTO partner_referrals(seller_id, referrer_seller_id, buyer_key, order_id, commission_amount, created_at)"
                " VALUES(?,?,?,?,?,?)",
                (int(seller_id), int(referrer_seller_id), str(buyer_key or ""),
                 str(order_id or ""), int(commission_amount or 0), _now_iso()))
            self._conn.commit()
            r = self._q1("SELECT * FROM partner_referrals ORDER BY id DESC LIMIT 1")
            return dict(r) if r else None

    def partner_referrals(self, seller_id: int = 0) -> list:
        sql = "SELECT * FROM partner_referrals"
        args = ()
        if seller_id:
            sql += " WHERE seller_id=? OR referrer_seller_id=?"
            args = (int(seller_id), int(seller_id))
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in self._q(sql, args)]

    # ---------------- push-подписки склада ----------------
    def wh_push_add(self, user_id: int, sub: dict):
        with _lock:
            key = json.dumps(sub, ensure_ascii=False)
            self._conn.execute("DELETE FROM wh_push_subs WHERE user_id=? AND sub=?",
                               (int(user_id), key))
            self._conn.execute("INSERT INTO wh_push_subs(user_id, sub, created_at) VALUES(?,?,?)",
                               (int(user_id), key, _now_iso()))
            self._conn.commit()

    def wh_push_remove(self, user_id: int, endpoint: str = "") -> int:
        with _lock:
            if endpoint:
                self._conn.execute(
                    "DELETE FROM wh_push_subs WHERE user_id=? AND sub LIKE ?",
                    (int(user_id), f"%{endpoint}%"))
            else:
                self._conn.execute("DELETE FROM wh_push_subs WHERE user_id=?", (int(user_id),))
            self._conn.commit()
            return self._conn.total_changes

    def wh_push_subs(self, user_id: int = 0) -> list:
        sql = "SELECT * FROM wh_push_subs"
        args = ()
        if user_id:
            sql += " WHERE user_id=?"
            args = (int(user_id),)
        out = []
        for r in self._q(sql, args):
            try:
                sub = json.loads(r["sub"])
                if isinstance(sub, dict):
                    out.append({**sub, "user_id": r["user_id"], "id": r["id"]})
            except Exception:
                continue
        return out

    # ---------------- массовое редактирование склада ----------------
    BULK_FIELDS = ("price", "old_price", "purchase_price", "stock", "in_stock",
                   "storage_location", "owner_name", "category", "on_showcase")

    def bulk_update_products(self, ids: list, patch: dict) -> int:
        data = {k: v for k, v in (patch or {}).items() if k in self.BULK_FIELDS}
        if not data:
            return 0
        n = 0
        with _lock:
            for pid in ids:
                p = self.get_product(int(pid))
                if p and not p.get("is_archived"):
                    self.update_product(int(pid), dict(data))
                    n += 1
            self._conn.commit()
        return n

    # ---------------- маркетплейс: подкатегории, поиск, избранное ----------------
    def moderate_content(self, content_id: int = 0, content_type: str = "product", text: str = "", image_url: str = "") -> dict:
        # Заглушка модерации ИИ: базовый скрининг текста и проверка фото
        banned_words = ["запрещено", "наркотики", "оружие", "подделка", "контрафакт", "пиратский"]
        text_lower = (text or "").lower()
        score = 0.0
        details = []
        for word in banned_words:
            if word in text_lower:
                score += 0.3
                details.append(f"Запрещённое слово: {word}")
        if image_url and (".jpg" not in image_url) and (".png" not in image_url) and (".jpeg" not in image_url) and (".webp" not in image_url):
            if not (image_url.startswith("http://") or image_url.startswith("https://")):
                score += 0.2
                details.append("Нет изображения или неподдерживаемый формат")
        result = "approved" if score < 0.3 else ("rejected" if score >= 0.6 else "pending")
        cur = self.db.execute(
            "INSERT INTO moderation_results (content_id, content_type, result, score, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (content_id, content_type, result, round(score, 2), "; ".join(details), str(__import__("datetime").datetime.now())))
        self.db.commit()
        return {"id": cur.lastrowid, "content_id": content_id, "result": result, "score": round(score, 2), "details": details}

    def moderation_status(self, content_id: int = 0, content_type: str = "") -> list:
        rows = self.db.execute("SELECT * FROM moderation_results WHERE 1=1").fetchall()
        out = [dict(r) for r in rows]
        if content_id:
            out = [r for r in out if r.get("content_id") == content_id]
        if content_type:
            out = [r for r in out if r.get("content_type", "").lower() == content_type.lower()]
        return out

    def add_label(self, product_id: int = 0, label_name: str = "", label_color: str = "#4f46e5") -> int:
        cur = self.db.execute(
            "INSERT INTO labels (product_id, label_name, label_color, created_at) VALUES (?, ?, ?, ?)",
            (product_id, label_name, label_color, str(__import__("datetime").datetime.now())))
        self.db.commit()
        return cur.lastrowid

    def get_labels(self, product_id: int = 0) -> list:
        rows = self.db.execute("SELECT * FROM labels WHERE 1=1").fetchall()
        out = [dict(r) for r in rows]
        if product_id:
            out = [r for r in out if r.get("product_id") == product_id]
        return out

    def campaigns(self, seller_id: int = 0, platform: str = "") -> list:
        rows = self.db.execute("SELECT * FROM campaigns WHERE 1=1").fetchall()
        out = [dict(r) for r in rows]
        if seller_id:
            out = [r for r in out if r.get("seller_id") == seller_id]
        if platform:
            out = [r for r in out if r.get("platform", "").lower() == platform.lower()]
        return out

    def create_campaign(self, seller_id: int = 0, platform: str = "yandex", title: str = "", budget: int = 0, creative_url: str = "", target_city: str = "") -> int:
        cur = self.db.execute(
            "INSERT INTO campaigns (seller_id, platform, title, budget, spent, status, creative_url, target_city, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (seller_id, platform, title, budget, 0, "draft", creative_url, target_city, str(__import__("datetime").datetime.now())))
        self.db.commit()
        return cur.lastrowid

    def update_campaign_status(self, campaign_id: int, status: str) -> bool:
        cur = self.db.execute("UPDATE campaigns SET status = ? WHERE id = ?", (status, campaign_id))
        self.db.commit()
        return cur.rowcount > 0

    def geo_search(self, query: str = "", city: str = "", radius_km: int = 50, limit: int = 30) -> list:
        """Простая заглушка гео-поиска: ищет товары с совпадением города или по названию."""
        city_lower = (city or "").lower().strip()
        out = []
        for p in self.products():
            if not p.get("in_stock"):
                continue
            match_city = True
            if city_lower:
                match_city = city_lower in (p.get("category") or "").lower() or city_lower in (p.get("name") or "").lower()
            if not match_city:
                continue
            score = search_score(p, query) if query else 10
            if query and score == 0:
                continue
            out.append(p)
        out.sort(key=lambda p: -search_score(p, query) if query else -p.get("price", 0))
        return out[:limit]

    def subcategories(self, category: str = "") -> list:
        """Подкатегории из таблицы catalog_cats; если для категории ничего нет —
        собирает из товаров (subcategory полей)."""
        rows = self._q("SELECT * FROM catalog_cats ORDER BY sort, id")
        out = []
        for r in rows:
            d = dict(r)
            d["cat_slug"] = slugify_ru(d.get("category") or "")
            out.append(d)
        known = {(r["category"], r["subcategory"]) for r in out}
        if category:
            # дополняем из товаров, чтобы подкатегории без SEO-настроек тоже были видны
            for p in self.products():
                sc = (p.get("subcategory") or "").strip()
                if p.get("category") == category and sc and (category, sc) not in known:
                    out.append({"id": 0, "category": category, "subcategory": sc,
                                "slug": slugify_ru(sc), "cat_slug": slugify_ru(category),
                                "seo_title": "", "seo_text": "", "sort": 0})
                    known.add((category, sc))
        return out

    def subcategory_by_slug(self, slug: str):
        r = self._q1("SELECT * FROM catalog_cats WHERE slug=?", (slug,))
        return dict(r) if r else None

    def upsert_subcategory(self, data: dict) -> dict:
        with _lock:
            category = str(data.get("category") or "").strip()
            subcategory = str(data.get("subcategory") or "").strip()
            if not category or not subcategory:
                raise ValueError("Укажите категорию и подкатегорию")
            slug = slugify_ru(str(data.get("slug") or "")) or slugify_ru(subcategory)
            seo_title = str(data.get("seo_title") or "").strip()
            seo_text = str(data.get("seo_text") or "").strip()
            sort = int(data.get("sort") or 0)
            if data.get("id"):
                # обновление существующей
                row = self._q1("SELECT * FROM catalog_cats WHERE id=?", (int(data["id"]),))
                if not row:
                    raise ValueError("Подкатегория не найдена")
                clash = self._q1("SELECT id FROM catalog_cats WHERE slug=? AND id<>?", (slug, int(data["id"])))
                if clash:
                    raise ValueError("Такой slug уже занят")
                self._conn.execute(
                    "UPDATE catalog_cats SET category=?, subcategory=?, slug=?, seo_title=?, seo_text=?, sort=?"
                    " WHERE id=?",
                    (category, subcategory, slug, seo_title, seo_text, sort, int(data["id"])))
            else:
                clash = self._q1("SELECT id FROM catalog_cats WHERE slug=?", (slug,))
                if clash:
                    raise ValueError("Подкатегория с таким slug уже существует")
                self._conn.execute(
                    "INSERT INTO catalog_cats(category, subcategory, slug, seo_title, seo_text, sort)"
                    " VALUES(?,?,?,?,?,?)",
                    (category, subcategory, slug, seo_title, seo_text, sort))
            self._conn.commit()
            r = self._q1("SELECT * FROM catalog_cats WHERE slug=?", (slug,))
            return dict(r) if r else None

    def delete_subcategory(self, sub_id: int) -> bool:
        with _lock:
            self._conn.execute("DELETE FROM catalog_cats WHERE id=?", (int(sub_id),))
            self._conn.commit()
            return self._conn.total_changes > 0

    def products_by_ids(self, ids: list) -> list:
        out = []
        for pid in ids:
            try:
                p = self.get_product(int(pid))
            except (ValueError, TypeError):
                continue
            if p and p.get("in_stock"):
                out.append(p)
        return out

    # ---------------- склад: быстрый вход (PIN/биометрия) ----------------
    def wh_session_create(self, user_id: int) -> str:
        """Создаёт секрет устройства для быстрого входа. Возвращает secret."""
        with _lock:
            secret = secrets.token_hex(32)
            self._conn.execute("INSERT INTO wh_sessions(user_id, secret, created_at, last_used) VALUES(?,?,?,?)",
                               (int(user_id), secret, _now_iso(), _now_iso()))
            self._conn.commit()
            return secret

    def wh_session_login(self, secret: str):
        """Проверяет секрет устройства и возвращает пользователя."""
        r = self._q1("SELECT * FROM wh_sessions WHERE secret=?", (str(secret or ""),))
        if not r:
            return None
        uid = int(dict(r)["user_id"])
        row = self._q1("SELECT * FROM wh_users WHERE id=?", (uid,))
        if not row:
            return None
        with _lock:
            self._conn.execute("UPDATE wh_sessions SET last_used=? WHERE secret=?",
                               (_now_iso(), str(secret)))
            self._conn.commit()
        return dict(row)

    def wh_session_revoke(self, user_id: int) -> int:
        with _lock:
            self._conn.execute("DELETE FROM wh_sessions WHERE user_id=?", (int(user_id),))
            self._conn.commit()
            return self._conn.total_changes

    def wh_cred_add(self, user_id: int, credential_id: str, public_key: str, sign_count: int = 0):
        with _lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO wh_credentials(user_id, credential_id, public_key, sign_count, created_at)"
                " VALUES(?,?,?,?,?)",
                (int(user_id), credential_id, public_key, int(sign_count), _now_iso()))
            self._conn.commit()

    def wh_cred_list(self, user_id: int) -> list:
        return [dict(r) for r in self._q("SELECT * FROM wh_credentials WHERE user_id=?", (int(user_id),))]

    def wh_cred_get(self, credential_id: str):
        r = self._q1("SELECT * FROM wh_credentials WHERE credential_id=?", (credential_id,))
        return dict(r) if r else None

    def wh_cred_update_counter(self, credential_id: str, sign_count: int):
        with _lock:
            self._conn.execute("UPDATE wh_credentials SET sign_count=? WHERE credential_id=?",
                               (int(sign_count), credential_id))
            self._conn.commit()

    def wh_cred_delete(self, user_id: int) -> int:
        with _lock:
            self._conn.execute("DELETE FROM wh_credentials WHERE user_id=?", (int(user_id),))
            self._conn.commit()
            return self._conn.total_changes

    # ---------------- статистика ----------------
    def stats(self) -> dict:
        paid_statuses = {"paid", "processing", "shipped", "delivered"}
        revenue = sum(o["total"] for o in self.orders(limit=5000) if o["status"] in paid_statuses)
        active = {"pending_payment", "paid", "processing", "shipped"}
        t = self.today_stats()
        return {
            "products": self._count("SELECT COUNT(*) c FROM products"),
            "orders": self._count("SELECT COUNT(*) c FROM orders"),
            "active": sum(1 for o in self.orders(limit=5000) if o["status"] in active),
            "revenue": revenue,
            "users": self.users_count(),
            "today_orders": t["orders"],
            "today_revenue": t["revenue"],
        }


store = Store()
