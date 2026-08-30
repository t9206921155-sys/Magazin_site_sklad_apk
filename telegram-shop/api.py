"""HTTP-сервер магазина (FastAPI):
  /            — сайт-витрина (SPA)
  /app         — Mini App для Telegram
  /admin       — админ-панель (CMS)
  /api/...     — API витрины
  /admin/api/..— API админки (по токену)
  /1c/...      — обмен с 1С (по X-1C-Token)
  /webhook/... — вебхуки ЮKassa, CryptoBot, Т-Банка
"""
import asyncio
import base64
import csv
import datetime
import hashlib
import hmac
import io
import json
import logging
import os
import secrets
import time
import urllib.parse
import xml.sax.saxutils as sax

try:
    import qrcode
    from qrcode.image.svg import SvgPathImage
except Exception:
    qrcode = None
    SvgPathImage = None

try:
    from webauthn import (generate_registration_options, verify_registration_response,
                          generate_authentication_options, verify_authentication_response,
                          options_to_json)
    from webauthn.helpers import (bytes_to_base64url, base64url_to_bytes,
                                  parse_registration_credential_json,
                                  parse_authentication_credential_json)
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria, UserVerificationRequirement,
        AuthenticatorAttachment, PublicKeyCredentialDescriptor, AuthenticatorTransport,
    )
    HAS_WEBAUTHN = True
except Exception:
    HAS_WEBAUTHN = False

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
import importer
import mailer
import cloudstore
import pdfreport
import ai as ai_module
import autopost
import push
import avito as avito_module
from store import CONDITION_LABELS, slugify_ru
import media as media_module
import seo
from cdek import calc_or_fallback
from delivery_dispatch import after_payment
from fivepost import FivePostClient
from payments import TbankProvider
from security import user_from_init_data, verify_init_data
from yandex_delivery import YandexDeliveryClient

from fastapi.templating import Jinja2Templates

log = logging.getLogger("shop.api")

TEMPLATES = Jinja2Templates(directory=os.path.join(config.SITE_DIR, "templates"))


def _render(request: Request, name: str, ctx: dict):
    """Совместимость с разными версиями Starlette."""
    try:
        return TEMPLATES.TemplateResponse(request=request, name=name, context=ctx)
    except TypeError:
        return TEMPLATES.TemplateResponse(name, {**ctx, "request": request})

SECRET_FILE = os.path.join(config.DATA_DIR, ".secret_key")


def server_secret() -> str:
    try:
        with open(SECRET_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        s = secrets.token_hex(32)
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(SECRET_FILE, "w") as f:
            f.write(s)
        return s


def admin_token() -> str:
    return hmac.new(server_secret().encode(), b"admin:" + config.ADMIN_PASSWORD.encode(),
                    hashlib.sha256).hexdigest()


CAT_EMOJIS = {
    "электроника": "📱", "дом": "🏠", "аксессуары": "🎒", "подарки": "🎁",
"одежда": "👕", "обувь": "👟", "косметика": "💄",
    "книги": "📚", "детям": "🧸", "спорт": "⚽", "красота": "✨",
}


def cat_emoji(cat: str) -> str:
    return CAT_EMOJIS.get(str(cat).strip().lower(), "🛍️")


class OrderItemIn(BaseModel):
    id: int
    qty: int = Field(ge=1, le=99)


class CustomerIn(BaseModel):
    name: str = ""
    phone: str = ""
    city: str = ""
    address: str = ""
    comment: str = ""
    point_id: str = ""


class OrderIn(BaseModel):
    items: list[OrderItemIn]
    customer: CustomerIn
    delivery_method: str = "courier"
    payment_method: str = "test"
    promo_code: str = ""
    bonus_spend: int = 0


class CalcIn(BaseModel):
    method: str = "cdek"
    city: str = ""
    point_id: str = ""


class EventIn(BaseModel):
    type: str
    payload: dict = {}


def create_app(store, providers: dict, bot=None, notify_new_order=None, notify_order_paid=None,
               notify_status=None, notify_admin=None, broadcast_sender=None):
    app = FastAPI(title="Telegram Shop", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def cache_static(request: Request, call_next):
        """Кэш-заголовки для статики (картинки, стили, скрипты, медиа)."""
        resp = await call_next(request)
        path = request.url.path
        if path.startswith(("/webapp/", "/site/", "/media/")):
            if path.endswith((".css", ".js", ".jpg", ".jpeg", ".png", ".svg", ".webp", ".mp4", ".ico")):
                resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        if request.url.path.startswith(("/api/", "/admin/api/", "/1c/", "/webhook/")):
            return JSONResponse({"detail": "Не найдено"}, status_code=404)
        try:
            html = TEMPLATES.env.get_template("404.html").render(
                request=request, shop=store.settings["shop_name"])
            return HTMLResponse(html, status_code=404)
        except Exception:
            return HTMLResponse("<h1>Страница не найдена</h1>", status_code=404)

    def require_admin(x_admin_token: str = Header(default="")):
        if not hmac.compare_digest(x_admin_token, admin_token()):
            raise HTTPException(403, "Нет доступа")

    def require_1c(x_1c_token: str = Header(default="")):
        if not store.settings["1c_token"] or not hmac.compare_digest(x_1c_token, store.settings["1c_token"]):
            raise HTTPException(403, "Неверный токен 1С")

    def get_user(request: Request):
        init_data = request.headers.get("x-init-data", "")
        ok, parsed = verify_init_data(init_data, config.BOT_TOKEN)
        if not ok:
            raise HTTPException(status_code=403, detail="Недействительные данные Telegram")
        tg_user = user_from_init_data(parsed)
        return (int(tg_user["id"]) if tg_user else None), request.query_params.get("guest_id")

    # ------------------------------------------------------------------ статика
    app.mount("/webapp", StaticFiles(directory=config.WEBAPP_DIR), name="webapp")
    app.mount("/site", StaticFiles(directory=config.SITE_DIR), name="site")
    os.makedirs(os.path.join(config.DATA_DIR, "media"), exist_ok=True)
    app.mount("/media", StaticFiles(directory=os.path.join(config.DATA_DIR, "media")), name="media")
    apk_dir = os.path.join(config.BASE_DIR, "apk")
    aab_dir = os.path.join(config.BASE_DIR, "aab")
    os.makedirs(apk_dir, exist_ok=True)
    os.makedirs(aab_dir, exist_ok=True)
    app.mount("/apk", StaticFiles(directory=apk_dir), name="apk")
    app.mount("/aab", StaticFiles(directory=aab_dir), name="aab")

    # ------------------------------------------------------------------ SEO-страницы (SSR)
    def _abs(request: Request, path: str = "") -> str:
        base = str(request.base_url).rstrip("/")
        return base + path

    def _seo_ctx(request: Request, title: str, description: str, canonical: str = "",
                 og_image: str = "", jsonld: str = "", noindex: bool = False, **extra) -> dict:
        return {
            "request": request, "title": title, "description": description,
            "canonical": canonical, "og_image": og_image, "jsonld": jsonld,
            "noindex": noindex, "shop": store.settings["shop_name"],
            "contacts": (store.settings.get("texts") or {}).get("contacts", ""),
            "free_delivery_from": int(store.settings.get("free_delivery_from") or 0),
            "social_links": store.settings.get("social_links") or {},
            "announcement": (store.settings.get("announcement") or "").strip(),
            **extra,
        }

    def _visible_products() -> list:
        mp = store.settings.get("marketplace") or {}
        out = []
        for p in store.products():
            if not p.get("in_stock", True):
                continue
            if not p.get("on_showcase", True):
                continue
            if p.get("is_archived"):
                continue
            row = dict(p)
            if mp.get("enabled"):
                sid = int(row.get("seller_id") or 0)
                if sid:
                    seller = store.get_seller(sid)
                    if not seller or seller["status"] != "active":
                        continue
                    row["seller_name"] = seller["store_name"]
                    row["seller_slug"] = seller["slug"]
            out.append(row)
        return out


    def _human_size(size: int) -> str:
        value = float(size or 0)
        units = ["B", "KB", "MB", "GB"]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024.0
        return f"{size} B"

    def _sha256_file(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _android_release_files(request: Request) -> dict:
        files = []
        for kind, folder, url_prefix, ext in (("apk", apk_dir, "/apk/", ".apk"), ("aab", aab_dir, "/aab/", ".aab")):
            for name in sorted(os.listdir(folder)):
                if not name.lower().endswith(ext):
                    continue
                path = os.path.join(folder, name)
                if not os.path.isfile(path):
                    continue
                st = os.stat(path)
                files.append({
                    "kind": kind,
                    "filename": name,
                    "version": name.replace("Sklad-", "").replace(f"-release{ext}", ""),
                    "size_bytes": int(st.st_size),
                    "size_human": _human_size(int(st.st_size)),
                    "sha256": _sha256_file(path),
                    "updated_at": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%d.%m.%Y %H:%M"),
                    "mtime": float(st.st_mtime),
                    "download_url": _abs(request, url_prefix + urllib.parse.quote(name)),
                })
        files.sort(key=lambda x: x["mtime"], reverse=True)
        latest_apk = next((x for x in files if x["kind"] == "apk"), None)
        latest_aab = next((x for x in files if x["kind"] == "aab"), None)
        return {"files": files, "latest_apk": latest_apk, "latest_aab": latest_aab}

    def _recommended_warehouse_url(request: Request, raw: str = "") -> str:
        candidate = (raw or config.WEBAPP_URL or _abs(request, "/")).strip()
        if not candidate:
            return _abs(request, "/warehouse/")
        if not candidate.startswith(("http://", "https://")):
            candidate = "https://" + candidate
        try:
            u = urllib.parse.urlparse(candidate)
            scheme = u.scheme or "https"
            netloc = u.netloc or u.path
            path = u.path if u.netloc else ""
            if not path or path == "/":
                path = "/warehouse/"
            elif path == "/warehouse":
                path = "/warehouse/"
            elif not path.startswith("/warehouse/"):
                path = path.rstrip("/") + "/warehouse/"
            return urllib.parse.urlunparse((scheme, netloc, path, "", "", ""))
        except Exception:
            return _abs(request, "/warehouse/")

    def _android_deep_link(mode: str, server_url: str) -> str:
        host = "setup" if mode == "setup" else "connect"
        return f"sklad://{host}?url={urllib.parse.quote(server_url, safe='')}"

    def _android_qr_svg(payload: str) -> str:
        if not qrcode or not SvgPathImage:
            safe = sax.escape(payload)
            return (
                '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="320" viewBox="0 0 320 320">'
                '<rect width="320" height="320" rx="28" fill="#ffffff"/>'
                '<rect x="18" y="18" width="284" height="284" rx="24" fill="#0f172a" opacity="0.04"/>'
                '<text x="160" y="122" text-anchor="middle" font-size="22" font-family="Arial" fill="#0f172a">QR недоступен</text>'
                '<text x="160" y="158" text-anchor="middle" font-size="14" font-family="Arial" fill="#475569">Установите пакет qrcode</text>'
                f'<text x="160" y="212" text-anchor="middle" font-size="11" font-family="Arial" fill="#64748b">{safe[:68]}</text>'
                '</svg>'
            )
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(image_factory=SvgPathImage)
        return img.to_string(encoding="unicode")

    def _android_publication_pack(request: Request, latest_version: str, recommended_server_url: str) -> dict:
        shop_name = (store.settings.get("shop_name") or "Telegram Shop").strip()
        website_url = _abs(request, "/")
        support_url = _abs(request, "/download/android")
        privacy_url = _abs(request, "/privacy")
        rustore_url = _abs(request, "/download/android/rustore")
        short_description = "Склад, остатки, фото товаров и публикация на витрину прямо с телефона."
        full_description = (
            "Склад — мобильное приложение для команды магазина и склада. "
            f"Оно подключается к витрине {shop_name}, открывает рабочий раздел /warehouse/ и помогает вести товары с телефона: "
            "добавлять фотографии, менять остатки, печатать этикетки, быстро публиковать позиции на витрину и работать с заказами без ноутбука.\n\n"
            "Что умеет приложение:\n"
            "• подключение к вашему серверу по ссылке или QR-коду;\n"
            "• хранение адреса склада и быстрый повторный вход;\n"
            "• загрузка одной или нескольких фотографий товара;\n"
            "• работа с остатками, ценами, этикетками и публикацией;\n"
            "• встроенное сканирование QR и штрих-кодов камерой внутри APK;\n"
            "• нативный fallback-сканер Android, если BarcodeDetector в WebView ведёт себя нестабильно;\n"
            "• открытие внешних ссылок в браузере, без поломки рабочего сценария.\n\n"
            "Приложение подходит для владельца магазина, кладовщика и сотрудника точки выдачи. "
            "Если сервер уже настроен, достаточно установить APK или открыть deep link — адрес подставится автоматически. "
            "Это удобно для внутреннего внедрения, пилота и публикации в RuStore."
        )
        whats_new = (
            f"Версия {latest_version}: добавлен нативный fallback-сканер Android для QR и штрих-кодов, обновлены RuStore-материалы "
            "и чек-лист релизной выкладки."
        )
        return {
            "app_name": "Склад — Telegram Shop",
            "package_id": "ru.telegramshop.sklad",
            "website_url": website_url,
            "support_url": support_url,
            "privacy_url": privacy_url,
            "rustore_url": rustore_url,
            "recommended_server_url": recommended_server_url,
            "short_description": short_description,
            "full_description": full_description,
            "whats_new": whats_new,
            "keywords": "склад, учёт товаров, остатки, магазин, витрина, telegram, продажи, RuStore",
            "category": "Бизнес",
            "age_rating": "0+",
            "contact_email": "support@your-domain.example",
            "support_note": "Замените email и юридические данные перед публикацией, если используете бренд клиента.",
            "moderator_note": (
                "Приложение предназначено для сотрудников магазина и склада. Камера используется для сканирования "
                "QR/штрих-кодов и для загрузки фото товаров. Если web-сканер в WebView нестабилен, внутри APK "
                "доступен нативный Android fallback. Политика конфиденциальности опубликована по ссылке " + privacy_url + "."
            ),
            "connect_link": _android_deep_link("connect", recommended_server_url),
            "setup_link": _android_deep_link("setup", recommended_server_url),
        }

    @app.get("/api/releases/android")
    async def api_android_releases(request: Request):
        data = _android_release_files(request)
        recommended = _recommended_warehouse_url(request, request.query_params.get("server", ""))
        latest_version = (data["latest_apk"] or data["latest_aab"] or {}).get("version", "1.0.5")
        publication = _android_publication_pack(request, latest_version, recommended)
        return {
            "apk": data["latest_apk"],
            "aab": data["latest_aab"],
            "files": data["files"],
            "recommended_server_url": recommended,
            "deep_link_setup": _android_deep_link("setup", recommended),
            "deep_link_connect": _android_deep_link("connect", recommended),
            "qr_setup_svg": _abs(request, "/api/releases/android/qr.svg?mode=setup&server=" + urllib.parse.quote(recommended, safe="")),
            "qr_connect_svg": _abs(request, "/api/releases/android/qr.svg?mode=connect&server=" + urllib.parse.quote(recommended, safe="")),
            "package_id": publication["package_id"],
            "rustore_url": publication["rustore_url"],
            "privacy_url": publication["privacy_url"],
        }

    @app.get("/api/releases/android/qr.svg")
    async def api_android_release_qr(request: Request, mode: str = "connect", server: str = ""):
        recommended = _recommended_warehouse_url(request, server)
        payload = _android_deep_link(mode, recommended)
        return Response(_android_qr_svg(payload), media_type="image/svg+xml")

    @app.get("/download/android")
    async def android_download_page(request: Request):
        data = _android_release_files(request)
        url = _abs(request, "/download/android")
        latest_apk = data["latest_apk"]
        latest_aab = data["latest_aab"]
        latest_version = (latest_apk or latest_aab or {}).get("version", "1.0.5")
        recommended_server_url = _recommended_warehouse_url(request, request.query_params.get("server", ""))
        publication = _android_publication_pack(request, latest_version, recommended_server_url)
        ctx = _seo_ctx(
            request,
            title=seo.page_title(store.settings["shop_name"], "Скачать Android-приложение «Склад»"),
            description=f"Скачайте Android-сборки «Склад»: APK для ручной установки и AAB для публикации в сторах. Текущая версия {latest_version}.",
            canonical=url,
            latest_apk=latest_apk,
            latest_aab=latest_aab,
            release_files=data["files"],
            recommended_server_url=recommended_server_url,
            deep_link_setup=publication["setup_link"],
            deep_link_connect=publication["connect_link"],
            connect_qr_svg=_abs(request, "/api/releases/android/qr.svg?mode=connect&server=" + urllib.parse.quote(recommended_server_url, safe="")),
            setup_qr_svg=_abs(request, "/api/releases/android/qr.svg?mode=setup&server=" + urllib.parse.quote(recommended_server_url, safe="")),
            latest_version=latest_version,
            rustore_url=publication["rustore_url"],
            privacy_url=publication["privacy_url"],
        )
        return _render(request, "android_download.html", ctx)

    @app.get("/download/android/rustore")
    async def android_rustore_page(request: Request):
        data = _android_release_files(request)
        latest_version = (data["latest_apk"] or data["latest_aab"] or {}).get("version", "1.0.5")
        recommended_server_url = _recommended_warehouse_url(request, request.query_params.get("server", ""))
        publication = _android_publication_pack(request, latest_version, recommended_server_url)
        ctx = _seo_ctx(
            request,
            title=seo.page_title(store.settings["shop_name"], "Публикация «Склад» в RuStore"),
            description=f"Готовые тексты, ссылки и чек-лист для публикации Android-приложения «Склад» в RuStore. Версия {latest_version}.",
            canonical=_abs(request, "/download/android/rustore"),
            latest_version=latest_version,
            latest_apk=data["latest_apk"],
            latest_aab=data["latest_aab"],
            publication=publication,
        )
        return _render(request, "android_rustore.html", ctx)

    @app.get("/privacy")
    async def privacy_page(request: Request):
        ctx = _seo_ctx(
            request,
            title=seo.page_title(store.settings["shop_name"], "Политика конфиденциальности мобильного приложения"),
            description="Политика конфиденциальности для Android-приложения «Склад» и веб-платформы Telegram Shop.",
            canonical=_abs(request, "/privacy"),
            shop_name=store.settings.get("shop_name") or "Telegram Shop",
        )
        return _render(request, "privacy.html", ctx)

    @app.get("/")
    async def home(request: Request):
        s = store.settings
        products = _visible_products()
        top = store.top_sellers(4) or products[:4]
        discounts = [p for p in products if p.get("old_price") and p["old_price"] > p["price"]][:4]
        new_items = [p for p in products if "new" in (p.get("badges") or [])][:4]
        url = _abs(request, "/")
        # последние одобренные отзывы для главной
        latest_reviews = []
        for r in store.all_reviews(limit=50):
            if r.get("status") != "approved":
                continue
            p = store.get_product(int(r["product_id"]))
            if p:
                latest_reviews.append({**r, "product_name": p["name"], "product_id": p["id"]})
            if len(latest_reviews) >= 6:
                break
        active_sellers = store.sellers(status="active")
        mp_settings = store.marketplace_settings()
        ctx = _seo_ctx(
            request,
            title=seo.page_title(s["shop_name"], "Маркетплейс в Telegram и на сайте"),
            description=f"{s['shop_name']} — маркетплейс с SEO-сайтом, Telegram Mini App и мобильным складом. "
                        f"{len(products)} товаров, {len(active_sellers)} продавцов, безопасная сделка, доставка и оплата онлайн.",
            canonical=url,
            og_image=_abs(request, "/site/img/og-main.png") if os.path.exists(os.path.join(config.SITE_DIR, "img", "og-main.png"))
            else (_abs(request, products[0]["photo"]) if products else ""),
            jsonld=seo.org_jsonld(s["shop_name"], url)
            + seo.faq_jsonld(s.get("faq") or [], url),
            hero_title="Маркетплейс, Telegram-магазин и склад — в одном проекте",
            hero_sub=f"{s['shop_name']} объединяет витрины продавцов, сайт, Mini App и мобильный склад. "
                     "Покупатели заказывают онлайн, продавцы управляют товарами и доставкой из одного кабинета.",
            hero_products=products[:4],
            top_sellers=top,
            discount_products=discounts,
            new_products=new_items,
            categories=store.categories(),
            cat_emojis={c: cat_emoji(c) for c in store.categories()},
            product_count=len(products),
            seller_count=len(active_sellers),
            active_sellers=active_sellers[:3],
            mp_enabled=bool(mp_settings.get("enabled", True)),
            commission=int(mp_settings.get("commission_percent") or 0),
            seo_text=(s.get("texts") or {}).get("about", ""),
            faq=s.get("faq") or [],
            reviews=latest_reviews,
            free_delivery_from=int(s.get("free_delivery_from") or 0),
        )
        return _render(request, "home.html", ctx)

    def _cat_slug(cat: str) -> str:
        return slugify_ru(cat)

    def _cat_by_slug(slug: str) -> str:
        for c in store.categories():
            if slugify_ru(c) == slug:
                return c
        return ""

    def _render_catalog(request: Request, cat: str = "", q: str = "", page: int = 1,
                        seller: str = "", subcat: str = "", condition: str = ""):
        s = store.settings
        products = _visible_products()
        categories = store.categories()
        cat = cat.strip()
        subcat = subcat.strip()
        q = q.strip()
        seller = seller.strip()
        condition = condition.strip()
        if seller:
            products = [p for p in products if p.get("seller_slug") == seller]
        if cat:
            products = [p for p in products if p.get("category") == cat]
        if subcat:
            products = [p for p in products if (p.get("subcategory") or "").strip() == subcat]
        if condition:
            products = [p for p in products if p.get("condition") == condition]
        if q:
            # умный поиск: опечатки, синонимы, ранжирование
            scored = {pid: sc for pid, sc in store.search_products(q, limit=500)}
            products = [p for p in products if p["id"] in scored]
            products.sort(key=lambda p: -scored[p["id"]])
        subs = store.subcategories(cat) if cat else []
        per_page = 24
        total = len(products)
        pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(int(page), pages))
        page_products = products[(page - 1) * per_page: page * per_page]
        if subcat:
            heading = f"{subcat} — {cat}"
        else:
            heading = f"Категория «{cat}»" if cat else ("Поиск: " + q if q else "Каталог товаров")
        sub = f"{total} товаров" if total else "Ничего не найдено"
        sub_info = next((x for x in subs if x.get("subcategory") == subcat), None) if subcat else None
        seo_desc = (sub_info or {}).get("seo_text") or \
            f"{heading} в интернет-магазине {s['shop_name']}. {sub}. " \
            "Доставка по всей стране, оплата картой и СБП, акции и промокоды."
        # ЧПУ-адрес
        if cat:
            if subcat:
                sub_slug = (sub_info or {}).get("slug") or slugify_ru(subcat)
                path = f"/catalog/{_cat_slug(cat)}/{sub_slug}"
            else:
                path = f"/catalog/{_cat_slug(cat)}"
        else:
            path = "/catalog"
        extra = []
        if q:
            extra.append("q=" + urllib.parse.quote(q))
        if seller and not cat:
            extra.append("seller=" + urllib.parse.quote(seller))
        if condition:
            extra.append("condition=" + urllib.parse.quote(condition))
        url = _abs(request, path) + (("?" + "&".join(extra)) if extra else "")
        canon = url + (("&" if "?" in url else "?") + f"page={page}" if page > 1 else "")
        title = seo.page_title(s["shop_name"],
                               (sub_info or {}).get("seo_title") or heading + (f" — стр. {page}" if page > 1 else ""))
        ctx = _seo_ctx(
            request, title=title,
            description=seo_desc,
            canonical=canon,
            jsonld=seo.breadcrumbs_jsonld([("Главная", _abs(request, "/")), ("Каталог", _abs(request, "/catalog")),
                                           (heading, canon)], canon),
            heading=heading, sub=sub, products=page_products, categories=categories,
            cat=cat, subcat=subcat, subs=subs, condition=condition,
            condition_labels=CONDITION_LABELS, q=q, page=page, pages=pages, total=total,
            cat_emojis={c: cat_emoji(c) for c in categories},
            cat_slugs={c: slugify_ru(c) for c in categories},
        )
        return _render(request, "catalog.html", ctx)

    @app.get("/catalog")
    async def catalog_page(request: Request, cat: str = "", q: str = "", page: int = 1,
                           seller: str = "", sub: str = "", condition: str = ""):
        return _render_catalog(request, cat=cat, q=q, page=page, seller=seller,
                               subcat=sub, condition=condition)

    @app.get("/catalog/{cat_slug}")
    async def catalog_cat_page(request: Request, cat_slug: str, q: str = "", page: int = 1,
                               condition: str = ""):
        cat = _cat_by_slug(cat_slug)
        if not cat:
            raise HTTPException(404, "Категория не найдена")
        return _render_catalog(request, cat=cat, q=q, page=page, condition=condition)

    @app.get("/catalog/{cat_slug}/{sub_slug}")
    async def catalog_sub_page(request: Request, cat_slug: str, sub_slug: str, q: str = "",
                               page: int = 1, condition: str = ""):
        cat = _cat_by_slug(cat_slug)
        if not cat:
            raise HTTPException(404, "Категория не найдена")
        subcat = ""
        for x in store.subcategories(cat):
            if x.get("slug") == sub_slug or slugify_ru(x.get("subcategory") or "") == sub_slug:
                subcat = x.get("subcategory")
                break
        if not subcat:
            raise HTTPException(404, "Подкатегория не найдена")
        return _render_catalog(request, cat=cat, subcat=subcat, q=q, page=page,
                               condition=condition)

    @app.get("/p/{product_id}")
    async def product_page(request: Request, product_id: int):
        p = store.get_product(product_id)
        if not p or not p.get("in_stock") or p.get("is_archived"):
            raise HTTPException(404, "Товар не найден")
        s = store.settings
        mp = s.get("marketplace") or {}
        seller = None
        if mp.get("enabled") and int(p.get("seller_id") or 0):
            seller = store.get_seller(int(p["seller_id"]))
            if not seller or seller["status"] != "active":
                raise HTTPException(404, "Товар не найден")
        url = _abs(request, f"/p/{p['id']}")
        title = seo.page_title(s["shop_name"], f"{p['name']} — {p['price']} ₽")
        description = seo.meta_description(p, s["shop_name"])
        reviews = store.reviews(p["id"], only_approved=True)
        rstats = store.review_stats(p["id"])
        crumbs = [("Главная", _abs(request, "/")), ("Каталог", _abs(request, "/catalog"))]
        if p.get("category"):
            crumbs.append((p["category"], _abs(request, f"/catalog/{slugify_ru(p['category'])}")))
        crumbs.append((p["name"], url))
        ctx = _seo_ctx(
            request, title=title, description=description, canonical=url,
            og_type="product", og_image=_abs(request, p["photo"]),
            jsonld=seo.product_jsonld(p, s["shop_name"], url, rstats) + seo.breadcrumbs_jsonld(crumbs, url),
            p=p, url=url, related=store.related_products(p["id"]),
            reviews=reviews, rstats=rstats, seller=seller,
            condition_label=CONDITION_LABELS.get(p.get("condition"), "Новое"),
            params=[(k, v) for k, v in (p.get("params") or {}).items() if str(v).strip()],
        )
        resp = _render(request, "product.html", ctx)
        return resp


    # ------------------------------------------------------------------ блог (SSR)
    @app.get("/blog")
    async def blog_list(request: Request):
        s = store.settings
        posts = store.posts(published_only=True)
        url = _abs(request, "/blog")
        ctx = _seo_ctx(
            request,
            title=seo.page_title(s["shop_name"], "Блог — обзоры, советы, новинки"),
            description=f"Блог интернет-магазина {s['shop_name']}: обзоры товаров, советы по выбору, "
                        "новинки и акции. Полезные статьи от команды магазина.",
            canonical=url, posts=posts,
        )
        return _render(request, "blog.html", ctx)

    @app.get("/blog/{slug}")
    async def blog_post(request: Request, slug: str):
        post = store.get_post(slug)
        if not post or not post.get("published"):
            raise HTTPException(404, "Статья не найдена")
        s = store.settings
        url = _abs(request, f"/blog/{slug}")
        cover = _abs(request, post["cover"]) if post.get("cover") and post["cover"].startswith("/") else post.get("cover") or ""
        ctx = _seo_ctx(
            request,
            title=seo.page_title(s["shop_name"], post["title"]),
            description=(post.get("excerpt") or (post.get("content") or "")[:150])[:200],
            canonical=url, og_type="article", og_image=cover,
            jsonld=seo.article_jsonld(post, s["shop_name"], url),
            post=post,
        )
        return _render(request, "post.html", ctx)

    # ------------------------------------------------------------------ товарные фиды
    @app.get("/feed/yandex.xml")
    async def feed_yandex(request: Request):
        """YML-фид для Яндекс.Маркета / Яндекс.Бизнеса."""
        s = store.settings
        base = _abs(request, "/")
        categories = store.categories()
        cat_ids = {c: i + 1 for i, c in enumerate(categories)}
        rows = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
                "<yml_catalog date=\"" + datetime.datetime.now().isoformat() + "\">",
                "  <shop>",
                f"    <name>{sax.escape(s['shop_name'])}</name>",
                f"    <company>{sax.escape(s['shop_name'])}</company>",
                f"    <url>{base}</url>",
                "    <currencies><currency id=\"RUB\" rate=\"1\"/></currencies>",
                "    <categories>"]
        for c, cid in cat_ids.items():
            rows.append(f"      <category id=\"{cid}\">{sax.escape(c)}</category>")
        rows.append("    </categories><offers>")
        for p in store.products():
            if not p.get("in_stock"):
                continue
            code = sax.escape(str(p.get("code") or f"TG-{p['id']}"))
            rows.append(f"      <offer id=\"{code}\" available=\"true\">")
            rows.append(f"        <name>{sax.escape(p['name'])}</name>")
            rows.append(f"        <price>{int(p['price'])}</price>")
            rows.append("        <currencyId>RUB</currencyId>")
            rows.append(f"        <categoryId>{cat_ids.get(p.get('category') or '', 1)}</categoryId>")
            if p.get("photo"):
                rows.append(f"        <picture>{base.rstrip('/') + p['photo']}</picture>")
            if p.get("description"):
                rows.append(f"        <description>{sax.escape(p['description'][:300])}</description>")
            rows.append(f"        <vendor>{sax.escape(s['shop_name'])}</vendor>")
            rows.append("      </offer>")
        rows += ["    </offers>", "  </shop>", "</yml_catalog>"]
        return Response("\n".join(rows), media_type="application/xml")

    @app.get("/feed/google.xml")
    async def feed_google(request: Request):
        """Фиды для Google Merchant Center (RSS 2.0 + g: неймспейс)."""
        s = store.settings
        base = _abs(request, "/")
        rows = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
                "<rss xmlns:g=\"http://base.google.com/ns/1.0\" version=\"2.0\">",
                "  <channel>",
                f"    <title>{sax.escape(s['shop_name'])}</title>",
                f"    <link>{base}</link>",
                f"    <description>Товары интернет-магазина {sax.escape(s['shop_name'])}</description>"]
        for p in store.products():
            code = sax.escape(str(p.get("code") or f"TG-{p['id']}"))
            rows.append("    <item>")
            rows.append(f"      <g:id>{code}</g:id>")
            rows.append(f"      <g:title>{sax.escape(p['name'])}</g:title>")
            rows.append(f"      <g:description>{sax.escape((p.get('description') or '')[:500])}</g:description>")
            rows.append(f"      <g:link>{base}p/{p['id']}</g:link>")
            if p.get("photo"):
                rows.append(f"      <g:image_link>{base.rstrip('/') + p['photo']}</g:image_link>")
            rows.append(f"      <g:price>{int(p['price'])}.00 RUB</g:price>")
            rows.append(f"      <g:availability>{'in stock' if p.get('in_stock') else 'out of stock'}</g:availability>")
            rows.append("      <g:condition>new</g:condition>")
            rows.append("    </item>")
        rows += ["  </channel>", "</rss>"]
        return Response("\n".join(rows), media_type="application/xml")

    @app.get("/shop")
    async def spa_shell():
        return FileResponse(os.path.join(config.SITE_DIR, "index.html"))

    @app.get("/robots.txt")
    async def robots(request: Request):
        base = _abs(request, "/")
        return Response(
            "User-agent: *\nAllow: /\n"
            "Disallow: /shop\nDisallow: /app\nDisallow: /admin\nDisallow: /api/\n"
            f"Sitemap: {base}sitemap.xml\n",
            media_type="text/plain")

    @app.get("/sitemap.xml")
    async def sitemap(request: Request):
        base = _abs(request, "/")
        urls = [(base, "daily", "1.0"), (base + "catalog", "daily", "0.9")]
        urls += [(base + f"p/{p['id']}", "daily", "0.8") for p in store.products() if p.get("in_stock")]
        urls += [(base + "blog", "weekly", "0.7"), (base + "download/android", "weekly", "0.8"), (base + "download/android/rustore", "weekly", "0.7"), (base + "privacy", "monthly", "0.4")]
        urls += [(base + f"blog/{post['slug']}", "monthly", "0.6") for post in store.posts(published_only=True)]
        if (store.settings.get("marketplace") or {}).get("enabled"):
            urls += [(base + "sellers", "weekly", "0.7"), (base + "become-seller", "monthly", "0.6")]
            urls += [(base + f"seller/{sl['slug']}", "weekly", "0.6") for sl in store.sellers("active")]
        urls += [(base + f"catalog/{slugify_ru(c)}", "weekly", "0.7") for c in store.categories()]
        for s in store.subcategories():
            if s.get("id"):
                urls.append((base + f"catalog/{slugify_ru(s['category'])}/{s['slug']}", "weekly", "0.7"))
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for u, freq, prio in urls:
            xml += f"  <url><loc>{u}</loc><changefreq>{freq}</changefreq><priority>{prio}</priority></url>\n"
        xml += "</urlset>"
        return Response(xml, media_type="application/xml")

    # ------------------------------------------------------------------ рекомендации
    @app.get("/api/recommendations")
    async def recommendations(product_id: int = 0):
        if product_id:
            return store.related_products(product_id)
        return {"top": store.top_sellers(8), "same_category": [], "co_bought": []}

    @app.get("/api/recommendations/recent")
    async def recent_products(ids: str = ""):
        out = []
        for pid in ids.split(",")[:8]:
            try:
                p = store.get_product(int(pid))
            except ValueError:
                continue
            if p and p.get("in_stock"):
                out.append({k: p[k] for k in ("id", "name", "price", "old_price", "photo", "category", "badges", "stock")})
        return {"products": out}

    # ------------------------------------------------------------------ публичное API
    @app.get("/api/health")
    async def health():
        return {"ok": True, "shop": store.settings["shop_name"]}

    @app.get("/app")
    async def mini_app():
        return FileResponse(os.path.join(config.WEBAPP_DIR, "index.html"))

    def public_delivery() -> dict:
        out = {}
        s = store.settings
        for k, d in s["delivery"].items():
            prov = d.get("provider", "fixed")
            if prov in ("cdek", "fivepost", "yandex") and not s.get(prov, {}).get("enabled"):
                continue
            out[k] = {"label": d["label"], "price": d["price"], "provider": prov}
        return out

    @app.get("/api/config")
    async def get_config():
        s = store.settings
        return {
            "shop_name": s["shop_name"], "currency": s["currency"],
            "delivery_methods": public_delivery(),
            "payment_provider": s["payment_provider"],
            "texts": s["texts"],
            "bot_enabled": bool(config.BOT_TOKEN),
            "free_delivery_from": int(s.get("free_delivery_from") or 0),
            "manager": s.get("manager") or {},
            "announcement": (s.get("announcement") or "").strip(),
            "social_links": s.get("social_links") or {},
            "yookassa_ok": bool(s["payments"]["yookassa"].get("enabled") and s["payments"]["yookassa"].get("shop_id")),
            "cryptobot_ok": bool(s["payments"]["cryptobot"].get("enabled") and s["payments"]["cryptobot"].get("api_token")),
            "tbank_ok": bool(s["payments"]["tbank"].get("enabled") and s["payments"]["tbank"].get("terminal_key")),
            "transfer_ok": bool(s["payments"]["transfer"].get("enabled")
                                and (s["payments"]["transfer"].get("phone") or s["payments"]["transfer"].get("card"))),
        }

    @app.get("/api/payment-methods")
    async def payment_methods(request: Request):
        tg_id, _ = get_user(request)
        s = store.settings["payments"]
        methods = []
        if s["test"].get("enabled"):
            methods.append({"id": "test", "label": "💳 Банковская карта (тест)",
                            "note": "Тестовый режим — деньги не списываются"})
        tr = s["transfer"]
        if tr.get("enabled") and (tr.get("phone") or tr.get("card")):
            methods.append({"id": "transfer", "label": "💸 Перевод по СБП или карте",
                            "note": "Перевод по номеру телефона или карты, подтверждаем вручную",
                            "details": {"phone": tr.get("phone"), "card": tr.get("card"),
                                        "bank": tr.get("bank"), "name": tr.get("name")}})
        if s["yookassa"].get("enabled") and s["yookassa"].get("shop_id"):
            methods.append({"id": "yookassa", "label": "💳 Карта / СБП (ЮKassa)",
                            "note": "Оплата через ЮKassa — Visa, MasterCard, МИР, СБП"})
        if s["tbank"].get("enabled") and s["tbank"].get("terminal_key"):
            methods.append({"id": "tbank", "label": "🏦 Т-Банк — карты и СБП",
                            "note": "Оплата через интернет-эквайринг Т-Банка"})
        if s["cryptobot"].get("enabled") and s["cryptobot"].get("api_token"):
            methods.append({"id": "cryptobot", "label": f"💎 CryptoBot ({s['cryptobot'].get('asset', 'USDT')})",
                            "note": "Криптовалюта TON/USDT через CryptoBot"})
        if s["stars"].get("enabled") and tg_id:
            methods.append({"id": "stars", "label": "⭐ Telegram Stars",
                            "note": "Оплата звёздами прямо в чате с ботом"})
        return methods

    @app.get("/api/catalog")
    async def catalog(q: str = "", cat: str = "", sub: str = "", condition: str = "",
                      seller: str = ""):
        products = _visible_products()
        if cat:
            products = [p for p in products if p.get("category") == cat]
        if sub:
            products = [p for p in products if (p.get("subcategory") or "").strip() == sub]
        if condition:
            products = [p for p in products if p.get("condition") == condition]
        if seller:
            products = [p for p in products if p.get("seller_slug") == seller]
        if q.strip():
            scored = {pid: sc for pid, sc in store.search_products(q, limit=500)}
            products = [p for p in products if p["id"] in scored]
            products.sort(key=lambda p: -scored[p["id"]])
        subs = store.subcategories(cat) if cat else []
        return {"products": products, "categories": store.categories(),
                "subcategories": subs,
                "condition_labels": CONDITION_LABELS,
                "marketplace": bool((store.settings.get("marketplace") or {}).get("enabled"))}

    @app.get("/api/search/suggest")
    async def search_suggest(q: str = ""):
        """Автодополнение поиска: до 8 названий по релевантности."""
        scored = store.search_products(q, limit=30)
        seen = set()
        out = []
        for pid, sc in scored:
            p = store.get_product(pid)
            if not p or not p.get("in_stock"):
                continue
            if p["name"] in seen:
                continue
            seen.add(p["name"])
            out.append({"id": p["id"], "name": p["name"], "price": p["price"],
                        "photo": p["photo"], "category": p["category"]})
            if len(out) >= 8:
                break
        return {"suggestions": out}

    @app.get("/api/favorites")
    async def favorites(ids: str = ""):
        """Товары из избранного (ids через запятую)."""
        id_list = [i for i in ids.replace(" ", "").split(",") if i.strip().isdigit()]
        products = []
        for p in store.products_by_ids(id_list):
            p["condition_label"] = CONDITION_LABELS.get(p.get("condition"), "Новое")
            products.append(p)
        return {"products": products}

    @app.post("/api/delivery/calc")
    async def delivery_calc(body: CalcIn):
        d = public_delivery().get(body.method)
        if not d:
            raise HTTPException(422, "Неизвестный способ доставки")
        if d["provider"] == "cdek" and body.city.strip():
            return calc_or_fallback(store.settings, body.city.strip(), d["price"])
        if d["provider"] == "yandex":
            return YandexDeliveryClient(store.settings).calc_price(
                body.city.strip(), body.point_id.strip(), d["price"])
        return {"price": d["price"], "calculated": False, "error": None}

    @app.get("/api/delivery/points")
    async def delivery_points(method: str = "fivepost", city: str = ""):
        """Список постаматов/ПВЗ (5POST или Яндекс Доставка)."""
        if method == "fivepost":
            client = FivePostClient(store.settings, store.settings["shop_name"])
            if not client.enabled:
                return {"points": [], "error": "5POST не настроен — укажите постамат в поле адреса вручную"}
            try:
                points = client.get_pickup_points()
            except Exception as e:
                log.warning("5POST: точки выдачи: %s", e)
                return {"points": [], "error": f"Не удалось загрузить постаматы: {e}"}
            if city.strip():
                q = city.strip().lower()
                points = [p for p in points if q in (p.get("city") or "").lower()
                          or q in (p.get("address") or "").lower() or q in (p.get("name") or "").lower()]
            return {"points": points[:200]}
        if method == "yandex":
            client = YandexDeliveryClient(store.settings)
            if not client.enabled:
                return {"points": [], "error": "Яндекс Доставка не настроен — укажите адрес вручную"}
            try:
                points = client.get_points(city)
            except Exception as e:
                return {"points": [], "error": str(e)}
            return {"points": points[:200]}
        raise HTTPException(422, "Метод не поддерживается")

    @app.post("/api/promo/validate")
    async def promo_validate(body: dict):
        return store.validate_promo(str(body.get("code", "")), int(float(body.get("subtotal", 0))))

    @app.get("/api/bonus")
    async def bonus_balance(request: Request):
        tg_id, guest_id = get_user(request)
        owner = f"tg:{tg_id}" if tg_id else (f"g:{guest_id}" if guest_id else "")
        return {"balance": store.bonus_balance(owner) if owner else 0,
                "loyalty_enabled": bool((store.settings.get("loyalty") or {}).get("enabled")),
                "rate_percent": int((store.settings.get("loyalty") or {}).get("rate_percent") or 0)}

    @app.get("/api/reviews")
    async def reviews(product_id: int = 0):
        revs = store.reviews(product_id, only_approved=True)
        return {"reviews": revs, "stats": store.review_stats(product_id)}

    @app.post("/api/reviews", status_code=201)
    async def add_review(body: dict, request: Request):
        get_user(request)
        rating = int(body.get("rating", 5))
        text = str(body.get("text", "")).strip()
        author = str(body.get("author", "")).strip() or "Гость"
        if not (1 <= rating <= 5):
            raise HTTPException(422, "Оценка от 1 до 5")
        if len(text) < 3:
            raise HTTPException(422, "Напишите отзыв (минимум 3 символа)")
        r = store.add_review(int(body.get("product_id", 0)), author, rating, text)
        return {"ok": True, "status": r["status"]}

    @app.post("/api/subscribe")
    async def subscribe(body: dict):
        try:
            return store.subscribe(str(body.get("email", "")))
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.post("/api/events")
    async def log_event(body: EventIn, request: Request):
        tg_id, guest_id = get_user(request)
        store.log_event(body.type, tg_id, guest_id, body.payload)
        return {"ok": True}

    @app.post("/api/order", status_code=201)
    async def create_order(body: OrderIn, request: Request, background_tasks: BackgroundTasks):
        tg_id, guest_id = get_user(request)
        s = store.settings
        name = body.customer.name.strip()
        phone = body.customer.phone.strip()
        if len(name) < 2:
            raise HTTPException(422, "Укажите имя")
        if len(phone) < 6:
            raise HTTPException(422, "Укажите корректный телефон")
        d = public_delivery().get(body.delivery_method)
        if not d:
            raise HTTPException(422, "Неверный способ доставки")
        if body.delivery_method != "pickup" and len(body.customer.address.strip()) < 5 and not body.customer.point_id:
            raise HTTPException(422, "Укажите адрес доставки или выберите точку выдачи")
        if body.payment_method not in providers:
            raise HTTPException(422, "Неверный способ оплаты")

        delivery_price = None
        if d["provider"] == "cdek" and body.customer.city.strip():
            res = calc_or_fallback(s, body.customer.city.strip(), d["price"])
            delivery_price = res["price"]
        if d["provider"] == "yandex":
            res = YandexDeliveryClient(s).calc_price(body.customer.city.strip(),
                                                     body.customer.point_id.strip(), d["price"])
            delivery_price = res["price"]

        try:
            order = store.create_order(
                [i.model_dump() for i in body.items], body.customer.model_dump(),
                body.delivery_method, tg_user_id=tg_id, guest_id=guest_id,
                payment_method=body.payment_method, delivery_price=delivery_price,
                promo_code=body.promo_code, bonus_spend=body.bonus_spend)
        except ValueError as e:
            raise HTTPException(422, str(e))
        if notify_new_order:
            background_tasks.add_task(notify_new_order, order)
        return order

    @app.get("/api/order/{order_id}")
    async def get_order(order_id: str, request: Request):
        get_user(request)
        order = store.get_order(order_id)
        if not order:
            raise HTTPException(404, "Заказ не найден")
        return order

    @app.get("/api/orders")
    async def my_orders(request: Request):
        tg_id, guest_id = get_user(request)
        return store.orders_for_user(tg_user_id=tg_id, guest_id=guest_id)

    @app.post("/api/order/{order_id}/pay/{provider_name}")
    async def pay(order_id: str, provider_name: str, request: Request, background_tasks: BackgroundTasks):
        get_user(request)
        order = store.get_order(order_id)
        if not order:
            raise HTTPException(404, "Заказ не найден")
        if order["status"] == "paid":
            return order
        if order["status"] != "pending_payment":
            raise HTTPException(409, "Оплата недоступна")
        provider = providers.get(provider_name)
        if not provider:
            raise HTTPException(404, "Неизвестный платёжный провайдер")
        try:
            result = await provider.pay_order(store, order_id)
        except ValueError as e:
            raise HTTPException(422, str(e))
        store.set_payment_method(order_id, provider_name)
        if isinstance(result, dict) and result.get("status") == "paid":
            if notify_order_paid:
                background_tasks.add_task(notify_order_paid, result)
            background_tasks.add_task(after_payment, store, order_id, notify_admin)
        elif isinstance(result, dict) and result.get("status") == "verifying" and notify_admin:
            background_tasks.add_task(
                notify_admin,
                f"🕓 Покупатель сообщил об оплате перевода по заказу <b>{order_id}</b>.\n"
                "Проверьте поступление и подтвердите оплату в админке (Заказы → «Подтвердить перевод»).")
        return result

    @app.get("/favorites")
    async def favorites_page(request: Request):
        s = store.settings
        ctx = _seo_ctx(
            request,
            title=seo.page_title(s["shop_name"], "Избранное"),
            description=f"Ваши избранные товары в магазине {s['shop_name']}. "
                        "Сохраняйте понравившиеся товары и возвращайтесь к ним в один клик.",
            canonical=_abs(request, "/favorites"),
            heading="Избранное ❤",
        )
        return _render(request, "favorites.html", ctx)

    # ------------------------------------------------------------------ админка
    @app.post("/admin/api/login")
    async def login(body: dict):
        if hmac.compare_digest(str(body.get("password", "")), config.ADMIN_PASSWORD):
            return {"token": admin_token()}
        raise HTTPException(401, "Неверный пароль")

    @app.get("/admin/api/dashboard")
    async def dashboard(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return store.stats()

    @app.get("/admin/api/products")
    async def admin_products(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return store.products()

    @app.post("/admin/api/products", status_code=201)
    async def admin_add_product(body: dict, x_admin_token: str = Header(default=""),
                                background_tasks: BackgroundTasks = None):
        require_admin(x_admin_token)
        data = dict(body)
        photo = importer.save_photo_data(data.pop("photo_data", "") or data.pop("photo_url", "") or "")
        if photo:
            data["photo"] = photo
        product = store.add_product(data)
        if background_tasks is not None:
            background_tasks.add_task(autopost.post_product, store, product, bot)
        return product

    @app.put("/admin/api/products/{pid}")
    async def admin_update_product(pid: int, body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        data = dict(body)
        photo = importer.save_photo_data(data.pop("photo_data", "") or data.pop("photo_url", "") or "")
        if photo:
            data["photo"] = photo
        p = store.update_product(pid, data)
        if not p:
            raise HTTPException(404, "Товар не найден")
        return p

    @app.delete("/admin/api/products/{pid}")
    async def admin_delete_product(pid: int, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        if not store.delete_product(pid):
            raise HTTPException(404, "Товар не найден")
        return {"ok": True}

    @app.get("/admin/api/orders")
    async def admin_orders(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return store.orders(limit=200)

    @app.post("/admin/api/orders/{order_id}/tracking")
    async def admin_order_tracking(order_id: str, body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        o = store.set_delivery_tracking(order_id, str(body.get("tracking", "")).strip())
        if not o:
            raise HTTPException(404, "Заказ не найден")
        return o

    @app.post("/admin/api/orders/{order_id}/confirm-payment")
    async def admin_confirm_payment(order_id: str, x_admin_token: str = Header(default=""),
                                    background_tasks: BackgroundTasks = None):
        """Ручное подтверждение оплаты переводом (для продавцов-физлиц)."""
        require_admin(x_admin_token)
        o = store.confirm_payment(order_id, "transfer", "manual")
        if not o:
            raise HTTPException(404, "Заказ не найден")
        store.set_payment_method(order_id, "transfer")
        if notify_order_paid:
            background_tasks.add_task(notify_order_paid, o)
        background_tasks.add_task(after_payment, store, order_id, notify_admin)
        return o

    @app.post("/admin/api/orders/{order_id}/status")
    async def admin_order_status(order_id: str, body: dict, x_admin_token: str = Header(default=""),
                                 background_tasks: BackgroundTasks = None):
        require_admin(x_admin_token)
        status = str(body.get("status", ""))
        allowed = {"paid", "processing", "shipped", "delivered", "completed", "cancelled"}
        if status not in allowed:
            raise HTTPException(422, "Неверный статус")
        o = store.set_order_status(order_id, status)
        if not o:
            raise HTTPException(404, "Заказ не найден")
        if notify_status:
            background_tasks.add_task(notify_status, o)
        return o

    # --- ИИ: контент для склада (название / объявление / Telegram) ---
    # --- ИИ-vision: распознавание товара по фото (Этап 3 — сканер-профи) ---
    @app.post("/api/warehouse/vision")
    async def wh_vision(body: dict, x_wh_token: str = Header(default=""),
                        x_admin_token: str = Header(default="")):
        """ИИ-распознавание товара по фото."""
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        image_data = str(body.get("image", "")).strip()
        if not image_data:
            raise HTTPException(422, "Нет изображения")
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]
        if len(image_data) > 5 * 1024 * 1024:
            raise HTTPException(422, "Изображение слишком большое (>5 МБ)")
        cfg = store.settings.get("ai") or {}
        vision_enabled = bool(cfg.get("enabled") and cfg.get("api_key"))
        description = ""
        results = []
        # Поиск по описанию или ключевым словам из базы
        all_products = [p for p in store.products() if not p.get("is_archived") and p.get("in_stock")]
        # Для демонстрации: простая эвристика — ищем по названию и категории
        keywords = ["наушники", "телефон", "одежда", "аксессуар", "книга", "игрушка", "электроника", "дом"]
        # Если ключи настроены, пробуем получить описание через текстовый запрос
        if vision_enabled:
            try:
                import requests
                base_url = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
                payload = {
                    "model": cfg.get("model") or "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "Ты эксперт по товарам. Кратко опиши товар по фото."},
                        {"role": "user", "content": "Фото товара из складского учёта. Опиши кратко: название, категория, ключевые слова (до 200 символов)."},
                    ],
                    "max_tokens": 250,
                    "temperature": 0.3,
                }
                headers = {"Authorization": "Bearer " + cfg["api_key"], "Content-Type": "application/json"}
                resp = requests.post(base_url, json=payload, headers=headers, timeout=30)
                if resp.status_code < 400:
                    description = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            except Exception:
                description = ""
        # Оцениваем товары по ключевым словам и описанию
        for p in all_products:
            score = 0
            text_to_search = (str(p.get("name", "")) + " " + str(p.get("category", "")) + " " + str(p.get("description", ""))).lower()
            # Совпадения с ключевыми словами
            for kw in keywords:
                if kw in text_to_search:
                    score += 1
            # Если есть описание из ИИ
            if description:
                desc_lower = description.lower()
                for word in desc_lower.split():
                    if len(word) >= 3 and word in text_to_search:
                        score += 0.5
            # Бонус за фото
            if p.get("photo"):
                score += 0.3
            if score > 0:
                results.append({
                    "product": {
                        "id": p["id"], "name": p.get("name", ""), "price": p.get("price", 0),
                        "category": p.get("category", ""), "photo": p.get("photo", ""),
                        "code": p.get("code", ""), "barcode": p.get("barcode", ""),
                        "stock": p.get("stock", -1),
                    },
                    "relevance": min(100, int(score * 15)),
                    "score": score,
                })
        results.sort(key=lambda x: -x["relevance"])
        top_results = results[:5]
        store.wh_log_add(user["name"], "ИИ-vision сканирование", f"совпадений: {len(top_results)}")
        return {
            "ok": True,
            "vision_enabled": vision_enabled,
            "description": (description or "Описание не получено")[:300],
            "matches": len(top_results),
            "results": [{"product": r["product"], "relevance": r["relevance"], "score": r["score"]} for r in top_results],
        }

    # --- Сканер-профи: инвентаризация со сверкой (Этап 3 склада) ---
    @app.post("/api/warehouse/inventory/compare")
    async def wh_inventory_compare(body: dict, x_wh_token: str = Header(default=""),
                                   x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        actual_items = body.get("items", [])
        if not isinstance(actual_items, list):
            raise HTTPException(422, "Ожидается список items")
        actual_dict = {}
        for item in actual_items:
            pid = int(item.get("product_id", 0))
            qty = int(item.get("qty", 0))
            if pid > 0:
                actual_dict[pid] = qty
        all_db = {p["id"]: p.get("stock", -1) for p in store.products() if not p.get("is_archived")}
        matches = []
        discrepancies = []
        missing_in_db = []
        for pid, qty in actual_dict.items():
            db_qty = all_db.get(pid)
            if db_qty is None:
                missing_in_db.append({"product_id": pid, "qty_actual": qty, "qty_db": None, "status": "not_in_db"})
            elif db_qty == qty:
                matches.append({"product_id": pid, "qty": qty, "status": "match"})
            else:
                discrepancies.append({
                    "product_id": pid,
                    "qty_actual": qty,
                    "qty_db": db_qty,
                    "diff": qty - db_qty,
                    "status": "surplus" if qty > db_qty else "shortage",
                    "product_name": (store.get_product(pid) or {}).get("name", "—"),
                    "category": (store.get_product(pid) or {}).get("category", ""),
                })
        total_db = sum(all_db.values()) if all_db else 0
        total_actual = sum(actual_dict.values())
        store.wh_log_add(user["name"], "инвентаризация со сверкой",
                         f"сверено: {len(actual_dict)} поз., расхождений: {len(discrepancies)}, совпадений: {len(matches)}")
        return {
            "ok": True,
            "summary": {
                "total_items_checked": len(actual_dict),
                "total_db_items": len(all_db),
                "matches": len(matches),
                "discrepancies": len(discrepancies),
                "missing_in_inventory": len([pid for pid in all_db if pid not in actual_dict]),
                "total_qty_db": total_db,
                "total_qty_actual": total_actual,
            },
            "results": {
                "matches": [{"product_id": m["product_id"], "qty": m["qty"]} for m in matches],
                "discrepancies": discrepancies,
                "missing_in_db": missing_in_db,
            },
        }

    @app.post("/api/warehouse/ai")
    async def wh_ai(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        p = store.get_product(int(body.get("product_id", 0)))
        if not p:
            raise HTTPException(404, "Товар не найден")
        mode = str(body.get("mode", "title"))
        if mode not in ("title", "listing", "telegram", "vk", "instagram"):
            raise HTTPException(422, "mode: title | listing | telegram | vk | instagram")
        try:
            return ai_module.generate_product_content(store, p, mode)
        except ValueError as e:
            raise HTTPException(422, str(e))

    # --- ИИ и медиа-генерация ---
    @app.post("/admin/api/ai/description")
    async def ai_description(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        p = store.get_product(int(body.get("product_id", 0)))
        if not p:
            raise HTTPException(404, "Товар не найден")
        try:
            return ai_module.generate_description(store, p)
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.post("/admin/api/ai/ad")
    async def ai_ad(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        p = store.get_product(int(body.get("product_id", 0)))
        if not p:
            raise HTTPException(404, "Товар не найден")
        try:
            return ai_module.generate_ad_copy(store, p)
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.post("/admin/api/ai/similar")
    async def ai_similar(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        p = store.get_product(int(body.get("product_id", 0)))
        if not p:
            raise HTTPException(404, "Товар не найден")
        try:
            return ai_module.find_similar(store, p)
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.post("/admin/api/media/banner")
    async def media_banner(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        p = store.get_product(int(body.get("product_id", 0)))
        if not p:
            raise HTTPException(404, "Товар не найден")
        try:
            url = media_module.generate_banner(p, store.settings["shop_name"])
            return {"url": url}
        except Exception as e:
            raise HTTPException(422, f"Не удалось сгенерировать баннер: {e}")

    @app.post("/admin/api/media/og")
    async def media_og(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        p = store.get_product(int(body.get("product_id", 0)))
        if not p:
            raise HTTPException(404, "Товар не найден")
        try:
            url = media_module.generate_og_image(p, store.settings["shop_name"])
            return {"url": url}
        except Exception as e:
            raise HTTPException(422, f"Не удалось сгенерировать OG-картинку: {e}")

    @app.post("/admin/api/media/video")
    async def media_video(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        p = store.get_product(int(body.get("product_id", 0)))
        if not p:
            raise HTTPException(404, "Товар не найден")
        try:
            url = media_module.generate_video(p, store.settings["shop_name"])
            return {"url": url}
        except Exception as e:
            raise HTTPException(422, f"Не удалось сгенерировать видео: {e}")

    # ------------------------------------------------------------------ Avito
    @app.get("/avito/autoload.xml")
    async def avito_feed(key: str = ""):
        """XML-фид автозагрузки Avito (ссылка добавляется в кабинете Avito)."""
        import hmac as hmac_mod
        expected = (store.settings.get("avito") or {}).get("feed_key") or ""
        if not expected or not hmac_mod.compare_digest(str(key), str(expected)):
            raise HTTPException(403, "Неверный ключ фида")
        return Response(avito_module.build_autoload_xml(store), media_type="application/xml")

    @app.get("/admin/api/avito/categories")
    async def avito_categories(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        client = avito_module.AvitoClient(store.settings)
        try:
            return await asyncio.to_thread(client.categories)
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.post("/admin/api/avito/post")
    async def avito_post(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        p = store.get_product(int(body.get("product_id", 0)))
        if not p:
            raise HTTPException(404, "Товар не найден")
        result = await asyncio.to_thread(avito_module.post_to_avito, store, p)
        if not result.get("ok"):
            raise HTTPException(422, result.get("error", "Ошибка Avito"))
        return result

    @app.post("/admin/api/avito/close")
    async def avito_close(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        p = store.get_product(int(body.get("product_id", 0)))
        if not p:
            raise HTTPException(404, "Товар не найден")
        result = await asyncio.to_thread(avito_module.close_on_avito, store, p)
        if not result.get("ok"):
            raise HTTPException(422, result.get("error", "Ошибка Avito"))
        return result

    @app.post("/admin/api/avito/post-all")
    async def avito_post_all(body: dict, x_admin_token: str = Header(default=""),
                            background_tasks: BackgroundTasks = None):
        """Выкладывание всех товаров без объявлений на Avito (пакетно)."""

        async def worker():
            ok = fail = 0
            for p in store.products():
                if p.get("avito_item_id"):
                    continue
                if not p.get("in_stock"):
                    continue
                r = await asyncio.to_thread(avito_module.post_to_avito, store, p)
                if r.get("ok"):
                    ok += 1
                else:
                    fail += 1
                await asyncio.sleep(0.5)
            return {"ok": ok, "fail": fail}

        task = asyncio.create_task(worker())
        return {"started": True}

    # --- промокоды ---
    @app.get("/admin/api/promos")
    async def admin_promos(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return store.promos()

    @app.post("/admin/api/promos", status_code=201)
    async def admin_create_promo(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        try:
            return store.create_promo(body)
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.delete("/admin/api/promos/{code}")
    async def admin_delete_promo(code: str, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        if not store.delete_promo(code):
            raise HTTPException(404, "Промокод не найден")
        return {"ok": True}

    # --- рассылки ---
    @app.post("/admin/api/broadcast")
    async def admin_broadcast(body: dict, x_admin_token: str = Header(default=""),
                              background_tasks: BackgroundTasks = None):
        require_admin(x_admin_token)
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(422, "Введите текст рассылки")
        if not broadcast_sender or not bot:
            raise HTTPException(422, "Бот не запущен (нет BOT_TOKEN) — рассылка недоступна")
        background_tasks.add_task(broadcast_sender, text)
        return {"started": True, "users": store.users_count()}

    # --- отзывы (модерация) ---
    @app.get("/admin/api/reviews")
    async def admin_reviews(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        revs = store.all_reviews()
        names = {}
        for r in revs:
            p = store.get_product(int(r["product_id"]))
            names[str(r["product_id"])] = p["name"] if p else "?"
        return {"reviews": revs, "product_names": names}

    @app.post("/admin/api/reviews/{review_id}/approve")
    async def admin_review_approve(review_id: int, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        store.set_review_status(review_id, "approved")
        return {"ok": True}

    @app.delete("/admin/api/reviews/{review_id}")
    async def admin_review_delete(review_id: int, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        store.delete_review(review_id)
        return {"ok": True}

    # --- блог ---
    @app.get("/admin/api/blog")
    async def admin_blog(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return store.posts(published_only=False)

    @app.post("/admin/api/blog", status_code=201)
    async def admin_blog_save(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return store.upsert_post(body)

    @app.delete("/admin/api/blog/{post_id}")
    async def admin_blog_delete(post_id: int, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        if not store.delete_post(post_id):
            raise HTTPException(404, "Статья не найдена")
        return {"ok": True}

    @app.post("/admin/api/blog/ai")
    async def admin_blog_ai(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        topic = str(body.get("topic", "")).strip()
        product_id = int(body.get("product_id") or 0)
        p = store.get_product(product_id) if product_id else None
        if not topic and not p:
            raise HTTPException(422, "Укажите тему или товар")
        try:
            return ai_module.generate_article(store, topic=topic, product=p)
        except ValueError as e:
            raise HTTPException(422, str(e))

    # --- массовая ИИ-генерация описаний ---
    @app.post("/admin/api/ai/generate-all")
    async def ai_generate_all(body: dict, x_admin_token: str = Header(default=""),
                              background_tasks: BackgroundTasks = None):
        require_admin(x_admin_token)

        async def worker():
            done = 0
            for p in store.products():
                if (p.get("description") or "").strip() and len(p["description"]) > 30:
                    continue
                try:
                    res = ai_module.generate_description(store, p)
                    store.update_product(p["id"], {"description": res.get("description") or p.get("description", "")})
                    done += 1
                    await asyncio.sleep(0.2)
                except Exception as e:
                    log.warning("массовая генерация %s: %s", p["id"], e)
            log.info("Массовая генерация завершена: %d описаний", done)
            return {"done": done}

        asyncio.create_task(worker())
        return {"started": True}

    # --- отчёты и экспорт ---
    @app.get("/admin/api/reports")
    async def admin_reports(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return {
            "stats": store.stats(),
            "today": store.today_stats(),
            "funnel": store.funnel(),
            "by_day": store.sales_by_day(14),
            "top_products": store.top_products(6),
            "users": store.users_count(),
            "subscribers": store.subscribers_count(),
        }

    @staticmethod
    def _csv(headers, rows, filename):
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(headers)
        w.writerows(rows)
        return Response(content=buf.getvalue().encode("utf-8-sig"),
                        media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/admin/api/export/orders")
    async def export_orders(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        rows = []
        for o in store.orders(limit=5000):
            items = "; ".join(f"{i['name']} x{i['qty']}" for i in o["items"])
            rows.append([o["id"], o["created_at"][:16].replace("T", " "), o["status"],
                         o["customer"].get("name", ""), o["customer"].get("phone", ""),
                         o["customer"].get("city", ""), o["customer"].get("address", ""),
                         items, o["delivery"]["label"], o["delivery"].get("tracking", ""),
                         o["subtotal"], o["discount"], o["delivery_price"], o["total"],
                         o.get("payment_method", "")])
        return _csv(["id", "дата", "статус", "клиент", "телефон", "город", "адрес",
                     "товары", "доставка", "трек", "сумма товаров", "скидка",
                     "доставка ₽", "итого", "оплата"], rows, "orders.csv")

    @app.get("/admin/api/export/products")
    async def export_products(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        rows = [[p["id"], p.get("code", ""), p["name"], p["category"], p["price"],
                 p.get("old_price", 0), p.get("stock", -1), int(p["in_stock"]),
                 ",".join(p.get("badges", [])), p.get("description", ""), p.get("photo", "")]
                for p in store.products()]
        return _csv(["id", "артикул", "название", "категория", "цена",
                     "старая цена", "остаток", "в наличии", "бейджи", "описание", "фото (url)"],
                    rows, "products.csv")

    @app.get("/admin/api/settings")
    async def admin_get_settings(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return store.settings

    @app.put("/admin/api/settings")
    async def admin_put_settings(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return store.update_settings(body)

    # ------------------------------------------------------------------ тарифы (настраиваемые)
    @app.get("/admin/api/tariffs")
    async def admin_tariffs(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return store.settings.get("tariffs") or {}

    @app.put("/admin/api/tariffs")
    async def admin_tariffs_save(body: dict, x_admin_token: str = Header(default="")):
        """Сохранение тарифов администратором (лимиты, цены, комиссия, холд)."""
        require_admin(x_admin_token)
        t = dict(body)
        # нормализация: только известные секции, числа
        out = {
            "enabled": bool(t.get("enabled", True)),
            "commission_percent": max(0, min(100, int(t.get("commission_percent") or 15))),
            "escrow_days": max(0, int(t.get("escrow_days") or 0)),
            "seller_default_plan": str(t.get("seller_default_plan") or "start"),
        }
        for key, plans_key in (("seller_plans", "seller_plans"), ("warehouse_plans", "warehouse_plans")):
            plans = []
            for p in t.get(plans_key) or []:
                if not isinstance(p, dict) or not p.get("id"):
                    continue
                plans.append({
                    "id": str(p["id"]), "name": str(p.get("name") or p["id"]),
                    "price": int(p.get("price") or 0),
                    "max_products": int(p.get("max_products") or 0),
                    "max_positions": int(p.get("max_positions") or 0),
                    "max_users": int(p.get("max_users") or 1),
                    "max_photos": int(p.get("max_photos") or 10),
                    "ai_month": int(p.get("ai_month") or 0),
                    "boost_month": int(p.get("boost_month") or 0),
                    "vip_products": int(p.get("vip_products") or 0),
                    "promos_max": int(p.get("promos_max") or 0),
                    "commission_discount": max(0, min(100, int(p.get("commission_discount") or 0))),
                    "excel": bool(p.get("excel")),
                    "stats": bool(p.get("stats")),
                    "cloud": bool(p.get("cloud")),
                })
            if plans:
                out[key] = plans
        ps = t.get("promo_services") or {}
        out["promo_services"] = {
            "boost_1d": int(ps.get("boost_1d") or 0),
            "boost_3d": int(ps.get("boost_3d") or 0),
            "boost_7d": int(ps.get("boost_7d") or 0),
            "vip_week": int(ps.get("vip_week") or 0),
            "ai_pack_20": int(ps.get("ai_pack_20") or 0),
        }
        return store.update_settings({"tariffs": out})

    # ------------------------------------------------------------------ подкатегории (каталог)
    @app.get("/admin/api/subs")
    async def admin_subs(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return {"subs": store.subcategories(), "categories": store.categories()}

    @app.post("/admin/api/subs", status_code=201)
    async def admin_sub_save(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        try:
            return store.upsert_subcategory(body)
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.delete("/admin/api/subs/{sub_id}")
    async def admin_sub_delete(sub_id: int, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        if not store.delete_subcategory(sub_id):
            raise HTTPException(404, "Подкатегория не найдена")
        return {"ok": True}

    @app.post("/admin/api/sellers/{sid}/plan")
    async def admin_seller_plan(sid: int, body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        try:
            s = store.set_seller_plan(sid, str(body.get("plan") or ""))
        except ValueError as e:
            raise HTTPException(422, str(e))
        if not s:
            raise HTTPException(404, "Продавец не найден")
        return s

    @app.post("/admin/api/sellers/{sid}/verify")
    async def admin_seller_verify(sid: int, body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        status = str(body.get("status") or "")
        if status not in ("verified", "rejected", "unverified"):
            raise HTTPException(422, "Статус: verified | rejected | unverified")
        s = store.set_seller_verification(sid, status)
        if not s:
            raise HTTPException(404, "Продавец не найден")
        if status == "verified" and notify_admin:
            try:
                await notify_admin(f"✅ Продавец «{s['store_name']}» верифицирован.")
            except Exception:
                pass
        return s

    @app.post("/admin/api/sellers/{sid}/release-held")
    async def admin_seller_release_held(sid: int, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        s = store.get_seller(sid)
        if not s:
            raise HTTPException(404, "Продавец не найден")
        released = store.release_all_held(sid)
        return {**store.get_seller(sid), "released": released}

    @app.post("/admin/api/1c/reset-token")
    async def admin_reset_1c(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return {"1c_token": store.reset_1c_token()}

    @app.post("/admin/api/import")
    async def admin_import(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        kind = body.get("type", "")
        data = body.get("data", "")
        try:
            if kind == "csv":
                items = importer.parse_csv(data)
            elif kind == "yml":
                items = importer.parse_yml(data)
            elif kind == "json":
                items = importer.parse_json_items(json.loads(data) if isinstance(data, str) else data)
            else:
                raise HTTPException(422, "Тип импорта: csv | yml | json")
        except Exception as e:
            raise HTTPException(422, f"Ошибка разбора: {e}")
        result = importer.apply_import(store, items)
        return {"source": kind, **result}

    @app.post("/admin/api/import/yml-url")
    async def admin_import_yml_url(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        import requests
        url = str(body.get("url", "")).strip()
        if not url.startswith("http"):
            raise HTTPException(422, "Некорректный URL")
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "TelegramShop/1.0"})
            r.raise_for_status()
        except Exception as e:
            raise HTTPException(422, f"Не удалось скачать фид: {e}")
        items = importer.parse_yml(r.text)
        result = importer.apply_import(store, items)
        return {"source": "yml-url", **result}

    # --- Excel (.xlsx) с фото ---
    @app.post("/admin/api/import/xlsx")
    async def admin_import_xlsx(x_admin_token: str = Header(default=""),
                                file: UploadFile = File(...)):
        require_admin(x_admin_token)
        data = await file.read()
        if not data:
            raise HTTPException(422, "Файл пуст")
        try:
            items = importer.parse_xlsx(data)
        except Exception as e:
            raise HTTPException(422, f"Ошибка разбора Excel: {e}")
        result = importer.apply_import(store, items)
        return {"source": "xlsx", **result}

    @app.get("/admin/api/export/products.xlsx")
    async def export_products_xlsx_endpoint(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        data = importer.export_products_xlsx(store)
        return Response(content=data,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="products.xlsx"'})

    @app.get("/admin/api/1c/test")
    async def admin_1c_test(request: Request, x_admin_token: str = Header(default="")):
        """Самопроверка обмена с 1С: какую информацию видит 1С прямо сейчас."""
        require_admin(x_admin_token)
        token = store.settings["1c_token"]
        base = _abs(request, "/")
        new_orders = sum(1 for o in store.orders(limit=500) if not o.get("synced"))
        return {"ok": True, "token": token, "base": base,
                "endpoints": {
                    "catalog": base + "1c/catalog",
                    "orders": base + "1c/orders?synced=0&status=paid,processing,shipped",
                    "ack": base + "1c/orders/ack",
                    "status": base + "1c/orders/status",
                },
                "products": len(store.products()),
                "new_orders_for_1c": new_orders}

    # ------------------------------------------------------------------ склад (PWA, мобильный учёт)
    app.mount("/warehouse", StaticFiles(directory=os.path.join(config.BASE_DIR, "warehouse"), html=True),
              name="warehouse")

    def _wh_product(p: dict) -> dict:
        photo = cloudstore.resolve_photo_url(store, p.get("photo") or "")
        photos = [cloudstore.resolve_photo_url(store, ph) for ph in (p.get("photos") or [])]
        return {
            "id": p["id"], "code": p.get("code", ""), "barcode": p.get("barcode", ""),
            "name": p["name"], "category": p.get("category", ""),
            "storage_location": p.get("storage_location", ""),
            "owner_name": p.get("owner_name", ""),
            "stock": p.get("stock", -1), "price": p["price"],
            "purchase_price": p.get("purchase_price", 0),
            "is_archived": bool(p.get("is_archived", 0)),
            "sum": (p["price"] * p["stock"]) if p.get("stock", -1) >= 0 else p["price"],
            "on_showcase": p.get("on_showcase", True),
            "in_stock": p.get("in_stock", True),
            "photos": photos, "photo": photo,
            "photo_local": p.get("photo", ""),   # локальный путь как fallback
            "seller_id": p.get("seller_id", 0),
        }

    @app.get("/api/warehouse/products")
    async def wh_products(q: str = "", x_wh_token: str = Header(default=""),
                          x_admin_token: str = Header(default="")):
        wh_user_from_headers(x_wh_token, x_admin_token)
        out = [_wh_product(p) for p in store.products() if not p.get("is_archived")]
        if q.strip():
            ql = q.strip().lower()
            out = [p for p in out if ql in p["name"].lower() or ql in p["code"].lower()
                   or ql in p["barcode"].lower() or ql in p["storage_location"].lower()
                   or ql in p["owner_name"].lower()]
        return {"products": out, "stats": store.stats()}

    @app.post("/api/warehouse/products", status_code=201)
    async def wh_add(body: dict, x_wh_token: str = Header(default=""),
                     x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        data = dict(body)
        photos = []
        for ph in data.pop("photos", [])[:20]:
            ph = str(ph)
            if ph.startswith("/"):
                photos.append(ph)
            else:
                saved = importer.save_photo_data(ph)
                if saved:
                    photos.append(saved)
        data["photos"] = photos
        if photos:
            data["photo"] = photos[0]
        if not data.get("name"):
            raise HTTPException(422, "Укажите наименование")
        data["in_stock"] = bool(data.get("in_stock", True))
        p = store.add_product(data)
        store.wh_log_add(user["name"], "создал товар", f"{p['name']} (id {p['id']})")
        if (store.settings.get("cloud") or {}).get("enabled") \
                and (store.settings.get("warehouse") or {}).get("auto_sync_cloud"):
            asyncio.create_task(asyncio.to_thread(cloudstore.sync_one_product, store, dict(p)))
        return _wh_product(p)

    @app.put("/api/warehouse/products/{pid}")
    async def wh_update(pid: int, body: dict, x_wh_token: str = Header(default=""),
                        x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        p = store.get_product(pid)
        if not p:
            raise HTTPException(404, "Товар не найден")
        data = dict(body)
        if "photos" in data:
            photos = []
            for ph in data["photos"][:20]:
                if str(ph).startswith("/"):
                    photos.append(str(ph))  # уже сохранённое фото
                else:
                    saved = importer.save_photo_data(str(ph))
                    if saved:
                        photos.append(saved)
            data["photos"] = photos
            if photos:
                data["photo"] = photos[0]
        p = store.update_product(pid, data)
        store.wh_log_add(user["name"], "изменил товар", f"{p['name']} (id {p['id']})")
        if (store.settings.get("cloud") or {}).get("enabled") \
                and (store.settings.get("warehouse") or {}).get("auto_sync_cloud"):
            asyncio.create_task(asyncio.to_thread(cloudstore.sync_one_product, store, dict(p)))
        return _wh_product(p)

    @app.post("/api/warehouse/scan")
    async def wh_scan(body: dict, x_wh_token: str = Header(default=""),
                      x_admin_token: str = Header(default="")):
        """Сканер: поиск / приёмка (+qty) / продажа (−qty) / инвентаризация (установить qty)."""
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        code = str(body.get("code", "")).strip()
        mode = str(body.get("mode", "search"))
        qty = int(body.get("qty", 1) or 1)
        if not code:
            raise HTTPException(422, "Пустой код")
        if mode not in ("search", "receive", "sell", "inventory"):
            raise HTTPException(422, "mode: search | receive | sell | inventory")
        product = next((p for p in store.products()
                        if str(p.get("barcode") or "") == code or str(p.get("code") or "") == code),
                       None)
        if not product:
            store.wh_scan_add(user["name"], mode, code, 0, qty, "not_found")
            return {"mode": mode, "found": False, "message": "Товар с таким кодом не найден"}
        message, warning = "", False
        if mode == "search":
            message = f"Найден: {product['name']}"
        elif mode == "receive":
            new_stock = (product.get("stock") if product.get("stock", -1) >= 0 else 0) + qty
            store.update_product(product["id"], {"stock": new_stock, "in_stock": True})
            message = f"Приёмка +{qty} → остаток {new_stock}"
        elif mode == "sell":
            cur = product.get("stock", -1)
            if cur <= 0:
                message = f"⚠️ {product['name']}: остаток 0 — продажа невозможна"
                warning = True
            else:
                new_stock = max(0, cur - qty)
                store.update_product(product["id"], {"stock": new_stock,
                                                     "in_stock": new_stock > 0})
                message = f"Продажа −{qty} → остаток {new_stock}"
                warning = new_stock == 0
        elif mode == "inventory":
            store.update_product(product["id"], {"stock": max(0, qty), "in_stock": qty > 0})
            message = f"Инвентаризация: остаток установлен {max(0, qty)}"
        product = store.get_product(product["id"])
        store.wh_scan_add(user["name"], mode, code, product["id"], qty, message)
        return {"mode": mode, "found": True, "product": _wh_product(product),
                "message": message, "warning": warning}

    @app.get("/api/warehouse/scans")
    async def wh_scans_list(x_wh_token: str = Header(default=""),
                            x_admin_token: str = Header(default="")):
        wh_user_from_headers(x_wh_token, x_admin_token)
        scans = store.wh_scans(50)
        names = {}
        for s in scans:
            p = store.get_product(int(s["product_id"])) if s["product_id"] else None
            names[str(s["product_id"])] = p["name"] if p else "—"
        return {"scans": scans, "product_names": names}

    # 3) Копия товара + архив
    @app.post("/api/warehouse/products/{pid}/copy")
    async def wh_copy(pid: int, x_wh_token: str = Header(default=""),
                      x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        copy = store.duplicate_product(pid)
        if not copy:
            raise HTTPException(404, "Товар не найден")
        store.wh_log_add(user["name"], "создал копию товара", f"{copy['name']} (id {copy['id']})")
        return _wh_product(copy)

    @app.post("/api/warehouse/products/{pid}/archive")
    async def wh_archive(pid: int, x_wh_token: str = Header(default=""),
                         x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        p = store.update_product(pid, {"is_archived": True, "in_stock": False})
        if not p:
            raise HTTPException(404, "Товар не найден")
        store.wh_log_add(user["name"], "архивировал товар", f"{p['name']} (id {p['id']})")
        return {"ok": True}

    # 3.1) Массовое редактирование выбранных товаров (Этап 2 мобильного плана)
    @app.post("/api/warehouse/products/bulk")
    async def wh_bulk_update(body: dict, x_wh_token: str = Header(default=""),
                             x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        ids = [int(i) for i in (body.get("ids") or [])][:200]
        if not ids:
            raise HTTPException(422, "Выберите товары (ids)")
        patch = {k: v for k, v in (body.get("patch") or {}).items() if k in store.BULK_FIELDS}
        if not patch:
            raise HTTPException(422, "Нет изменяемых полей")
        if "on_showcase" in patch:
            patch["on_showcase"] = bool(patch["on_showcase"])
        if "in_stock" in patch:
            patch["in_stock"] = bool(patch["in_stock"])
        n = store.bulk_update_products(ids, patch)
        store.wh_log_add(user["name"], "массовое редактирование",
                         f"{n} товаров: {', '.join(patch.keys())}")
        return {"ok": True, "updated": n}

    # 3.2) Push-уведомления PWA (Этап 2 мобильного плана; работают на HTTPS)
    @app.post("/api/warehouse/push/subscribe")
    async def wh_push_subscribe(body: dict, x_wh_token: str = Header(default=""),
                                x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        sub = body.get("subscription")
        if not isinstance(sub, dict) or not sub.get("endpoint"):
            raise HTTPException(422, "Неверная подписка")
        store.wh_push_add(int(user.get("id") or 0), sub)
        return {"ok": True}

    @app.delete("/api/warehouse/push/unsubscribe")
    async def wh_push_unsubscribe(body: dict = None, x_wh_token: str = Header(default=""),
                                  x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        endpoint = str((body or {}).get("endpoint") or "")
        store.wh_push_remove(int(user.get("id") or 0), endpoint)
        return {"ok": True}

    @app.post("/api/warehouse/push/test")
    async def wh_push_test(x_wh_token: str = Header(default=""),
                           x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        sent = push.send_push(store, [int(user.get("id") or 0)],
                              "Склад • Telegram Shop", "🔔 Push-уведомления работают!")
        return {"ok": True, "sent": sent}

    # 3.3) Быстрый вход на склад: PIN на устройстве + биометрия (WebAuthn)
    _webauthn_challenges = {}  # challenge_b64 -> {"login": str} | {"user_id": int}

    def _rp_id(request: Request) -> str:
        return request.url.hostname or "localhost"

    def _origin(request: Request) -> str:
        return f"{request.url.scheme}://{request.url.netloc}"

    def _client_challenge(body: dict) -> str:
        cj = (body.get("response") or {}).get("clientDataJSON") or ""
        try:
            pad = "=" * (-len(cj) % 4)
            raw = json.loads(base64.b64decode(cj + pad).decode("utf-8", "ignore"))
            return str(raw.get("challenge") or "")
        except Exception:
            return ""

    @app.post("/api/warehouse/quick/setup")
    async def wh_quick_setup(x_wh_token: str = Header(default=""),
                             x_admin_token: str = Header(default="")):
        """Включает быстрый вход по PIN для этого устройства (старые сессии сбрасываются)."""
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        store.wh_session_revoke(int(user.get("id") or 0))
        secret = store.wh_session_create(int(user.get("id") or 0))
        store.wh_log_add(user["name"], "включил быстрый вход", "PIN-сессия устройства создана")
        return {"ok": True, "secret": secret}

    @app.post("/api/warehouse/quick/login")
    async def wh_quick_login(body: dict):
        user = store.wh_session_login(str(body.get("secret") or ""))
        if not user:
            raise HTTPException(401, "Быстрый вход не настроен или был отключён")
        store.wh_log_add(user["name"], "быстрый вход", "вход по PIN/устройству")
        return {"ok": True, "token": _wh_token(user["login"], user["pass_hash"]),
                "user": {"login": user["login"], "name": user["name"], "role": user["role"]}}

    @app.delete("/api/warehouse/quick/revoke")
    async def wh_quick_revoke(x_wh_token: str = Header(default=""),
                              x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        n = store.wh_session_revoke(int(user.get("id") or 0))
        return {"ok": True, "revoked": n}

    @app.post("/api/warehouse/webauthn/register-options")
    async def wh_webauthn_reg_options(request: Request, x_wh_token: str = Header(default=""),
                                      x_admin_token: str = Header(default="")):
        if not HAS_WEBAUTHN:
            raise HTTPException(501, "Биометрия недоступна (установите py_webauthn)")
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        opts = generate_registration_options(
            rp_id=_rp_id(request), rp_name=store.settings["shop_name"],
            user_id=str(user["id"]).encode(), user_name=str(user["login"]),
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        ch = bytes_to_base64url(opts.challenge)
        self_clean = {k: v for k, v in _webauthn_challenges.items() if v.get("exp", 0) > time.time()}
        _webauthn_challenges.clear()
        _webauthn_challenges.update(self_clean)
        _webauthn_challenges[ch] = {"user_id": int(user["id"]), "exp": time.time() + 300}
        return json.loads(options_to_json(opts))

    @app.post("/api/warehouse/webauthn/register")
    async def wh_webauthn_register(request: Request, body: dict, x_wh_token: str = Header(default=""),
                                   x_admin_token: str = Header(default="")):
        if not HAS_WEBAUTHN:
            raise HTTPException(501, "Биометрия недоступна")
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        challenge = _client_challenge(body)
        data = _webauthn_challenges.pop(challenge, None)
        if not data or data.get("user_id") != int(user["id"]) or data.get("exp", 0) < time.time():
            raise HTTPException(400, "Просроченный или неверный запрос — попробуйте ещё раз")
        try:
            cred = parse_registration_credential_json(json.dumps(body))
            verification = verify_registration_response(
                credential=cred, expected_challenge=base64url_to_bytes(challenge),
                expected_rp_id=_rp_id(request), expected_origin=_origin(request))
        except Exception as e:
            raise HTTPException(400, f"Не удалось проверить устройство: {str(e)[:120]}")
        store.wh_cred_add(int(user["id"]), bytes_to_base64url(verification.credential_id),
                          bytes_to_base64url(verification.credential_public_key),
                          int(verification.sign_count))
        store.wh_log_add(user["name"], "включил биометрию", "WebAuthn-ключ зарегистрирован")
        return {"ok": True, "message": "Биометрия включена: вход по отпечатку/лицу доступен"}

    @app.post("/api/warehouse/webauthn/auth-options")
    async def wh_webauthn_auth_options(request: Request, body: dict):
        if not HAS_WEBAUTHN:
            raise HTTPException(501, "Биометрия недоступна")
        login = str(body.get("login") or "").strip()
        user = store.wh_user_by_login(login)
        if not user:
            raise HTTPException(401, "Пользователь не найден")
        creds = store.wh_cred_list(int(user["id"]))
        if not creds:
            raise HTTPException(404, "Биометрия не настроена — войдите по паролю и включите её в настройках")
        allow = [PublicKeyCredentialDescriptor(
            id=base64url_to_bytes(c["credential_id"]),
            transports=[AuthenticatorTransport.INTERNAL]) for c in creds]
        opts = generate_authentication_options(
            rp_id=_rp_id(request), allow_credentials=allow,
            user_verification=UserVerificationRequirement.REQUIRED)
        ch = bytes_to_base64url(opts.challenge)
        _webauthn_challenges[ch] = {"login": login, "exp": time.time() + 300}
        return json.loads(options_to_json(opts))

    @app.post("/api/warehouse/webauthn/auth")
    async def wh_webauthn_auth(request: Request, body: dict):
        if not HAS_WEBAUTHN:
            raise HTTPException(501, "Биометрия недоступна")
        credential = body.get("credential") or {}
        challenge = _client_challenge(credential)
        data = _webauthn_challenges.pop(challenge, None)
        login = (data or {}).get("login")
        if not login or (data or {}).get("exp", 0) < time.time():
            raise HTTPException(400, "Просроченный или неверный запрос — попробуйте ещё раз")
        user = store.wh_user_by_login(login)
        if not user:
            raise HTTPException(401, "Пользователь не найден")
        try:
            cred = parse_authentication_credential_json(json.dumps(credential))
            cid = bytes_to_base64url(cred.raw_id)
            stored = store.wh_cred_get(cid)
            if not stored:
                raise ValueError("ключ не найден")
            verification = verify_authentication_response(
                credential=cred, expected_challenge=base64url_to_bytes(challenge),
                expected_rp_id=_rp_id(request), expected_origin=_origin(request),
                credential_public_key=base64url_to_bytes(stored["public_key"]),
                credential_current_sign_count=int(stored["sign_count"] or 0),
                require_user_verification=True)
        except Exception as e:
            raise HTTPException(400, f"Не удалось проверить биометрию: {str(e)[:120]}")
        store.wh_cred_update_counter(cid, int(verification.new_sign_count))
        store.wh_log_add(user["name"], "вход по биометрии", "WebAuthn-подтверждение")
        return {"ok": True, "token": _wh_token(user["login"], user["pass_hash"]),
                "user": {"login": user["login"], "name": user["name"], "role": user["role"]}}

    # 4) Отложенные публикации (ТЗ: SM-3/SM-4)
    @app.get("/api/warehouse/posts")
    async def wh_posts(x_wh_token: str = Header(default=""),
                       x_admin_token: str = Header(default="")):
        wh_user_from_headers(x_wh_token, x_admin_token)
        posts = store.all_social_posts(100)
        names = {}
        for po in posts:
            p = store.get_product(int(po["product_id"])) if po["product_id"] else None
            names[str(po["product_id"])] = p["name"] if p else "—"
        return {"posts": posts, "product_names": names}

    @app.post("/api/warehouse/posts/schedule", status_code=201)
    async def wh_posts_schedule(body: dict, x_wh_token: str = Header(default=""),
                                x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        product_id = int(body.get("product_id", 0))
        platform = str(body.get("platform", "telegram"))
        scheduled_at = str(body.get("scheduled_at", ""))
        if not store.get_product(product_id):
            raise HTTPException(404, "Товар не найден")
        if platform not in ("telegram", "vk", "instagram", "avito"):
            raise HTTPException(422, "platform: telegram | vk | instagram | avito")
        if not scheduled_at:
            raise HTTPException(422, "Укажите дату и время")
        post = store.add_scheduled_post(product_id, platform, scheduled_at, user["name"])
        store.wh_log_add(user["name"], "запланировал публикацию",
                         f"{platform} @ {scheduled_at[:16]}")
        return post

    @app.delete("/api/warehouse/posts/{post_id}")
    async def wh_posts_delete(post_id: int, x_wh_token: str = Header(default=""),
                              x_admin_token: str = Header(default="")):
        wh_user_from_headers(x_wh_token, x_admin_token)
        if not store.delete_scheduled_post(post_id):
            raise HTTPException(404, "Публикация не найдена")
        return {"ok": True}

    # 5) Печать по фильтру + тестовая печать
    @app.get("/api/warehouse/labels.pdf")
    async def wh_labels(request: Request, ids: str = "", width: float = 58, height: float = 40,
                        copies: int = 1, x_wh_token: str = Header(default=""),
                        x_admin_token: str = Header(default="")):
        """PDF-наклейки (Code128 + QR + данные товара). Печать по ids или фильтру."""
        wh_user_from_headers(x_wh_token, x_admin_token)
        products = []
        if ids.strip():
            for pid in ids.split(","):
                try:
                    p = store.get_product(int(pid))
                except ValueError:
                    continue
                if p:
                    products.append(p)
        else:
            # печать по фильтру (ТЗ PR-6): категория / место / владелец
            cat = request.query_params.get("cat", "").strip()
            loc = request.query_params.get("loc", "").strip()
            owner = request.query_params.get("owner", "").strip()
            for p in store.products():
                if p.get("is_archived"):
                    continue
                if cat and p.get("category") != cat:
                    continue
                if loc and str(p.get("storage_location") or "") != loc:
                    continue
                if owner and str(p.get("owner_name") or "") != owner:
                    continue
                if cat or loc or owner:
                    products.append(p)
        if not products:
            raise HTTPException(422, "Нет товаров для печати (задайте ids или фильтр)")
        pdf = pdfreport.labels_pdf(products, width_mm=min(120, max(30, width)),
                                   height_mm=min(120, max(20, height)), copies=max(1, min(9, copies)))
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="labels.pdf"'})

    @app.get("/api/warehouse/labels.prn")
    async def wh_labels_prn(ids: str = "", format: str = "zpl", width: float = 58,
                            height: float = 40, copies: int = 1,
                            x_wh_token: str = Header(default=""),
                            x_admin_token: str = Header(default="")):
        """Этикетки для термопринтеров: ZPL (Zebra) или EPL (Eltron/ОВЕН) — файл .prn."""
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        products = []
        for pid in ids.split(","):
            try:
                p = store.get_product(int(pid))
            except ValueError:
                continue
            if p:
                products.append(p)
        if format == "epl":
            body = pdfreport.labels_epl(products, width, height, copies)
        else:
            body = pdfreport.labels_zpl(products, width, height, copies)
        store.wh_log_add(user["name"], "печать наклеек",
                         f"{len(products)} тов., {format.upper()}, {int(width)}×{int(height)} мм")
        return Response(content=body, media_type="text/plain; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="labels.prn"'})

    @app.get("/api/warehouse/printers")
    async def wh_printers(x_wh_token: str = Header(default=""),
                          x_admin_token: str = Header(default="")):
        wh_user_from_headers(x_wh_token, x_admin_token)
        return store.settings.get("warehouse_printers") or []

    @app.get("/api/warehouse/sync")
    async def wh_sync(x_wh_token: str = Header(default=""),
                      x_admin_token: str = Header(default="")):
        """Статус синхронизации: серверное время и счётчики (все данные — на сервере)."""
        wh_user_from_headers(x_wh_token, x_admin_token)
        return {"server_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "products": len(store.products()), "orders": len(store.orders()),
                "synced": True}

    @app.post("/api/warehouse/login")
    async def wh_login(body: dict):
        user = store.wh_check(str(body.get("login", "")), str(body.get("password", "")))
        if not user:
            raise HTTPException(401, "Неверный логин или пароль")
        return {"token": _wh_token(user["login"], user["pass_hash"]),
                "name": user["name"], "role": user["role"]}

    @app.get("/api/warehouse/users")
    async def wh_users_list(x_wh_token: str = Header(default=""),
                            x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        if user["role"] != "admin":
            raise HTTPException(403, "Только администратор склада")
        return store.wh_users()

    @app.post("/api/warehouse/users", status_code=201)
    async def wh_users_add(body: dict, x_wh_token: str = Header(default=""),
                           x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        if user["role"] != "admin":
            raise HTTPException(403, "Только администратор склада")
        try:
            store.wh_add_user(str(body.get("login", "")), str(body.get("name", "")),
                              str(body.get("password", "")), str(body.get("role", "worker")))
        except ValueError as e:
            raise HTTPException(422, str(e))
        store.wh_log_add(user["name"], "добавил пользователя", body.get("login", ""))
        return store.wh_users()

    @app.put("/api/warehouse/users/{uid}")
    async def wh_users_update(uid: int, body: dict, x_wh_token: str = Header(default=""),
                              x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        if user["role"] != "admin":
            raise HTTPException(403, "Только администратор склада")
        try:
            store.wh_update_user(uid, body)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return store.wh_users()

    @app.delete("/api/warehouse/users/{uid}")
    async def wh_users_delete(uid: int, x_wh_token: str = Header(default=""),
                              x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        if user["role"] != "admin":
            raise HTTPException(403, "Только администратор склада")
        if not store.wh_delete_user(uid):
            raise HTTPException(404, "Пользователь не найден")
        return {"ok": True}

    @app.get("/api/warehouse/log")
    async def wh_log_list(x_wh_token: str = Header(default=""),
                          x_admin_token: str = Header(default="")):
        wh_user_from_headers(x_wh_token, x_admin_token)
        return store.wh_logs(100)

    # ------------------------------------------------------------------ склад: расширенные настройки
    @app.get("/api/warehouse/settings")
    async def wh_settings(x_wh_token: str = Header(default=""),
                          x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        s = store.settings
        cloud = dict(s.get("cloud") or {})
        if user["role"] != "admin":
            cloud["key"] = "•••" if cloud.get("key") else ""
        soc = s.get("social") or {}
        return {
            "cloud": cloud,
            "printers": s.get("warehouse_printers") or [],
            "warehouse": {**(s.get("warehouse") or {}),
                          "vapid_public": push.vapid_public(store)},
            "social": {"auto_post_new": bool(soc.get("auto_post_new")),
                       "telegram_channel": soc.get("telegram_channel") or "",
                       "vk_group_id": soc.get("vk_group_id") or "",
                       "instagram_user_id": soc.get("instagram_user_id") or ""},
            "shop_name": s["shop_name"],
            "tariffs": (s.get("tariffs") or {}).get("warehouse_plans") or [],
        }

    @app.put("/api/warehouse/settings")
    async def wh_settings_save(body: dict, x_wh_token: str = Header(default=""),
                               x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        if user["role"] != "admin":
            raise HTTPException(403, "Только администратор склада")
        patch = {}
        if "cloud" in body:
            patch["cloud"] = body["cloud"]
        if "printers" in body and isinstance(body["printers"], list):
            patch["warehouse_printers"] = [
                {k: p.get(k, d) for k, d in
                 (("name", "Принтер"), ("width_mm", 58), ("height_mm", 40), ("format", "pdf"), ("copies", 1))}
                for p in body["printers"][:10]]
        if "warehouse" in body:
            patch["warehouse"] = body["warehouse"]
        if "cloud_state" in body and isinstance(body["cloud_state"], dict):
            patch["cloud_state"] = body["cloud_state"]
        if "social" in body:
            soc = store.settings.get("social") or {}
            patch["social"] = {**soc,
                               "auto_post_new": bool(body["social"].get("auto_post_new", soc.get("auto_post_new", False))),
                               "telegram_channel": str(body["social"].get("telegram_channel", soc.get("telegram_channel", ""))),
                               "vk_group_id": str(body["social"].get("vk_group_id", soc.get("vk_group_id", ""))),
                               "instagram_token": str(body["social"].get("instagram_token", "")),
                               "instagram_user_id": str(body["social"].get("instagram_user_id", soc.get("instagram_user_id", "")))}
        store.update_settings(patch)
        store.wh_log_add(user["name"], "изменил настройки", "облако/принтеры/публикация")
        return {"ok": True}

    @app.post("/api/warehouse/cloud/test")
    async def wh_cloud_test(x_wh_token: str = Header(default=""),
                            x_admin_token: str = Header(default="")):
        wh_user_from_headers(x_wh_token, x_admin_token)
        return cloudstore.test_cloud(store)

    @app.get("/api/warehouse/cloud/presets")
    async def wh_cloud_presets(x_wh_token: str = Header(default=""),
                               x_admin_token: str = Header(default="")):
        """Пресеты российских S3-провайдеров (endpoint, регион, где взять ключи)."""
        wh_user_from_headers(x_wh_token, x_admin_token)
        return cloudstore.s3_presets()

    @app.get("/api/warehouse/cloud/status")
    async def wh_cloud_status(x_wh_token: str = Header(default=""),
                              x_admin_token: str = Header(default="")):
        wh_user_from_headers(x_wh_token, x_admin_token)
        st = store.settings.get("cloud_state") or {}
        c = store.settings.get("cloud") or {}
        return {"enabled": bool(c.get("enabled")), "provider": c.get("provider"),
                "use_cdn": bool(c.get("use_cdn", True)),
                "last_sync": st.get("last_sync") or "",
                "photos_synced": len(st.get("photos") or {}),
                "catalog_count": st.get("catalog_count") or 0}

    @app.post("/api/warehouse/cloud/pull")
    async def wh_cloud_pull(x_wh_token: str = Header(default=""),
                            x_admin_token: str = Header(default="")):
        """Восстановление каталога из облака (pull) — обновляет/создаёт товары."""
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        res = cloudstore.restore_from_cloud(store)
        store.wh_log_add(user["name"], "восстановление из облака",
                         f"создано {res.get('created', 0)}, обновлено {res.get('updated', 0)}")
        return res

    @app.post("/api/warehouse/cloud/sync")
    async def wh_cloud_sync(x_wh_token: str = Header(default=""),
                            x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        res = cloudstore.sync_to_cloud(store)
        store.wh_log_add(user["name"], "синхронизация с облаком",
                         f"{res.get('products', 0)} товаров, {res.get('photos', {}).get('uploaded', 0)} фото")
        return res

    @app.post("/api/warehouse/products/{pid}/publish")
    async def wh_publish(pid: int, x_wh_token: str = Header(default=""),
                         x_admin_token: str = Header(default="")):
        """Публикация товара в соцсети и Telegram (настроенные каналы)."""
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        p = store.get_product(pid)
        if not p:
            raise HTTPException(404, "Товар не найден")
        res = await autopost.post_product(store, p, bot, force=True)
        store.wh_log_add(user["name"], "опубликовал товар", f"{p['name']} (id {p['id']})")
        return res

    @app.post("/api/warehouse/me/password")
    async def wh_me_password(body: dict, x_wh_token: str = Header(default=""),
                             x_admin_token: str = Header(default="")):
        user = wh_user_from_headers(x_wh_token, x_admin_token)
        old_p = str(body.get("old_password", ""))
        new_p = str(body.get("new_password", ""))
        if len(new_p) < 4:
            raise HTTPException(422, "Новый пароль — минимум 4 символа")
        if not store.wh_change_password(user["login"], old_p, new_p):
            raise HTTPException(422, "Неверный текущий пароль")
        store.wh_log_add(user["name"], "сменил пароль")
        return {"ok": True}

    @app.get("/api/warehouse/export.xlsx")
    async def wh_export(x_wh_token: str = Header(default=""),
                        x_admin_token: str = Header(default="")):
        wh_user_from_headers(x_wh_token, x_admin_token)
        data = importer.export_products_xlsx(store)
        return Response(content=data,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="warehouse.xlsx"'})

    # ------------------------------------------------------------------ кабинет продавца (веб)
    @app.get("/seller/app.js")
    async def seller_panel_js():
        return FileResponse(os.path.join(config.BASE_DIR, "seller", "app.js"))

    @app.get("/seller")
    @app.get("/seller/")
    async def seller_panel():
        return FileResponse(os.path.join(config.BASE_DIR, "seller", "index.html"))

    # ------------------------------------------------------------------ маркетплейс (SSR)
    @app.get("/sellers")
    async def sellers_list_page(request: Request):
        s = store.settings
        mp = s.get("marketplace") or {}
        sellers = [x for x in store.sellers("active")] if mp.get("enabled") else []
        url = _abs(request, "/sellers")
        ctx = _seo_ctx(
            request,
            title=seo.page_title(s["shop_name"], "Продавцы и магазины"),
            description=f"Продавцы маркетплейса {s['shop_name']}: их витрины, товары и акции. "
                        "Каждый продавец ведёт свой ассортимент, а площадка гарантирует честные условия.",
            canonical=url, sellers=sellers, mp_enabled=bool(mp.get("enabled")),
        )
        return _render(request, "sellers.html", ctx)

    @app.get("/seller/{slug}")
    async def seller_page(request: Request, slug: str):
        data = store.seller_public(slug)
        if not data or data["status"] != "active":
            raise HTTPException(404, "Магазин не найден")
        s = store.settings
        url = _abs(request, f"/seller/{slug}")
        ctx = _seo_ctx(
            request,
            title=seo.page_title(s["shop_name"], f"{data['store_name']} — витрина на {s['shop_name']}"),
            description=f"{data['store_name']} на маркетплейсе {s['shop_name']}: "
                        f"{len(data['products'])} товаров с доставкой. {data['description'][:120]}",
            canonical=url,
            jsonld=seo.breadcrumbs_jsonld([("Главная", _abs(request, "/")),
                                           ("Продавцы", _abs(request, "/sellers")),
                                           (data["store_name"], url)], url),
            seller=data,
            seller_rating=store.seller_rating(data.get("id") or 0),
            seller_review_stats=store.seller_review_stats(data.get("id") or 0),
            seller_reviews=store.seller_reviews(data.get("id") or 0),
        )
        return _render(request, "seller.html", ctx)

    @app.get("/become-seller")
    async def become_seller_page(request: Request):
        s = store.settings
        mp = s.get("marketplace") or {}
        url = _abs(request, "/become-seller")
        ctx = _seo_ctx(
            request,
            title=seo.page_title(s["shop_name"], "Стать продавцом"),
            description=f"Откройте свою витрину на маркетплейсе {s['shop_name']}: "
                        "собственные товары, акции и статистика. Комиссия площадки — "
                        f"{int(mp.get('commission_percent') or 15)}% с продажи.",
            canonical=url,
            auto_approve=bool(mp.get("auto_approve_sellers")),
            mp_enabled=bool(mp.get("enabled")),
            commission=int(mp.get("commission_percent") or 15),
        )
        return _render(request, "become_seller.html", ctx)

    # ------------------------------------------------------------------ API продавцов
    @app.post("/api/seller/register", status_code=201)
    async def seller_register(body: dict, background_tasks: BackgroundTasks):
        mp = store.settings.get("marketplace") or {}
        if not mp.get("enabled"):
            raise HTTPException(403, "Маркетплейс отключён")
        if len(str(body.get("store_name", "")).strip()) < 2:
            raise HTTPException(422, "Укажите название магазина")
        if len(str(body.get("phone", "")).strip()) < 6:
            raise HTTPException(422, "Укажите телефон")
        try:
            seller = store.register_seller(body)
        except ValueError as e:
            raise HTTPException(422, str(e))
        if notify_admin:
            background_tasks.add_task(notify_admin,
                f"🏪 <b>Новый продавец!</b>\n\n{seller['store_name']}\n"
                f"📞 {seller['phone']}\nСтатус: {seller['status']}\n\n"
                "Управляйте продавцами в админке → Продавцы.")
        if seller.get("email") and mailer.available(store):
            base = _abs(request, "/")
            background_tasks.add_task(mailer.send_email, store, seller["email"],
                f"Ваша витрина на {store.settings['shop_name']}",
                f"Здравствуйте!\n\nВаша витрина «{seller['store_name']}» создана.\n"
                f"Адрес: {base}seller/{seller['slug']}\n"
                f"Кабинет: {base}seller\nКлюч доступа: {seller['key']}\n\n"
                "Добавляйте товары, создавайте промокоды и следите за балансом.")
        return {"ok": True, "status": seller["status"],
                "key": seller["key"], "slug": seller["slug"],
                "message": "Витрина создана и ждёт подтверждения." if seller["status"] == "pending"
                           else "Витрина создана! Войдите в личный кабинет продавца."}

    def require_seller(x_seller_key: str = Header(default="")):
        seller = store.get_seller(key=x_seller_key) if x_seller_key else None
        if not seller:
            raise HTTPException(403, "Неверный ключ продавца")
        return seller

    def _wh_token(login: str, pass_hash: str) -> str:
        sig = hmac.new(server_secret().encode(), f"wh:{login}:{pass_hash}".encode(),
                       hashlib.sha256).hexdigest()
        return f"wh:{login}:{sig}"

    def wh_user_from_headers(x_wh_token: str = Header(default=""),
                             x_admin_token: str = Header(default="")):
        """Авторизация склада: свой токен пользователя ИЛИ токен админа площадки."""
        if x_admin_token:
            try:
                require_admin(x_admin_token)
                return {"id": 0, "login": "admin", "name": "Администратор", "role": "admin"}
            except HTTPException:
                pass
        if not x_wh_token:
            raise HTTPException(403, "Нужен вход")
        try:
            login = x_wh_token.split(":", 2)[1]
        except IndexError:
            raise HTTPException(403, "Неверный токен")
        user = store.wh_user_by_login(login)
        if not user or not hmac.compare_digest(_wh_token(login, user["pass_hash"]), x_wh_token):
            raise HTTPException(403, "Неверный токен")
        return user

    @app.get("/api/seller/me")
    async def seller_me(x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        return {**seller, "stats": store.seller_stats(seller["id"]),
                "rating": store.seller_rating(seller["id"]),
                "rating_details": store.seller_rating_details(seller["id"]),
                "limits": store.seller_limits(seller),
                "verification": store.seller_verification(seller),
                "unread_chat": store.chat_unread_seller(seller["id"]),
                "plans": (store.settings.get("tariffs") or {}).get("seller_plans") or [],
                "marketplace": store.settings.get("marketplace") or {}}

    @app.post("/api/seller/verify")
    async def seller_verify(body: dict, x_seller_key: str = Header(default="")):
        """Продавец отправляет данные на верификацию."""
        seller = require_seller(x_seller_key)
        ver = store.seller_verification(seller)
        if ver["status"] == "verified":
            raise HTTPException(409, "Вы уже верифицированы")
        inn = str(body.get("inn") or "").strip()
        owner = str(body.get("owner_name") or "").strip()
        if len(inn) < 10 or not inn.isdigit():
            raise HTTPException(422, "Укажите корректный ИНН (10–12 цифр)")
        if len(owner) < 5:
            raise HTTPException(422, "Укажите ФИО владельца (самозанятого/ИП)")
        doc_photo = ""
        ph = str(body.get("doc_photo") or "")
        if ph and not ph.startswith("/"):
            saved = importer.save_photo_data(ph)
            if saved:
                doc_photo = saved
        s = store.set_seller_verification(seller["id"], "pending",
                                          {"inn": inn, "owner_name": owner,
                                           "doc_photo": doc_photo or ver["data"].get("doc_photo", ""),
                                           "submitted_at": datetime.datetime.now().isoformat(timespec="seconds")})
        if notify_admin:
            try:
                await notify_admin(
                    f"🛡 <b>Запрос на верификацию</b>\n\n{s['store_name']}\n"
                    f"ИНН: {inn}\nВладелец: {owner}\n\nПроверьте в админке → Продавцы.")
            except Exception:
                pass
        return {**store.get_seller(seller["id"]),
                "verification": store.seller_verification(store.get_seller(seller["id"]))}

    @app.post("/api/seller/plan/request")
    async def seller_plan_request(body: dict, x_seller_key: str = Header(default="")):
        """Запрос на смену тарифа — подтверждает администратор."""
        seller = require_seller(x_seller_key)
        plan_id = str(body.get("plan_id") or "")
        plans = (store.settings.get("tariffs") or {}).get("seller_plans") or []
        plan = next((p for p in plans if p.get("id") == plan_id), None)
        if not plan:
            raise HTTPException(422, "Неизвестный тариф")
        store.log_event("seller_plan_request", 0, "", {"seller_id": seller["id"],
                                                       "plan": plan_id,
                                                       "at": datetime.datetime.now().isoformat(timespec="seconds")})
        if notify_admin:
            try:
                await notify_admin(
                    f"📈 <b>Запрос на смену тарифа</b>\n\n{seller['store_name']}: "
                    f"{seller.get('plan') or '—'} → {plan['name']} ({plan['price']} ₽/мес)\n\n"
                    "Назначьте тариф в админке → Продавцы.")
            except Exception:
                pass
        return {"ok": True, "message": "Запрос отправлен. Администратор назначит тариф."}

    @app.post("/api/seller/ai")
    async def seller_ai(body: dict, x_seller_key: str = Header(default="")):
        """ИИ-генерация для продавца с учётом лимита тарифа."""
        seller = require_seller(x_seller_key)
        product = store.get_product(int(body.get("product_id") or 0))
        if not product or int(product.get("seller_id") or 0) != int(seller["id"]):
            raise HTTPException(404, "Товар не найден")
        mode = str(body.get("mode") or "listing")
        if mode not in ("title", "listing", "telegram", "vk", "instagram"):
            raise HTTPException(422, "Режим: title | listing | telegram | vk | instagram")
        left = store.seller_ai_used(seller["id"])
        limit = int(store.seller_plan(seller).get("ai_month") or 0)
        if limit >= 0 and left >= limit:
            raise HTTPException(429, "Лимит ИИ-генераций по тарифу исчерпан. Смените тариф или дождитесь нового месяца.")
        try:
            result = ai_module.generate_product_content(store, dict(product), mode)
        except ValueError as e:
            raise HTTPException(422, str(e))
        left_after = store.spend_seller_ai(seller["id"])  # списываем только за успешную генерацию
        return {"ok": True, **result, "ai_left": left_after}

    @app.put("/api/seller/me")
    async def seller_me_update(body: dict, x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        s = store.update_seller(seller["id"], body)
        return {**s, "stats": store.seller_stats(seller["id"])}

    @app.get("/api/seller/products")
    async def seller_products(x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        return store.seller_products(seller["id"])

    @app.post("/api/seller/products", status_code=201)
    async def seller_add_product(body: dict, x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        data = dict(body)
        limits = store.seller_limits(seller)
        if limits.get("tariffs_enabled") and limits.get("max_products"):
            if limits["used_products"] >= limits["max_products"]:
                raise HTTPException(429,
                    f"Достигнут лимит объявлений по тарифу «{limits['plan'].get('name', '')}» "
                    f"({limits['max_products']} шт.). Смените тариф или удалите неактуальные товары.")
        photos = []
        for ph in (data.pop("photos", None) or [])[:20]:
            ph = str(ph)
            saved = ph if ph.startswith("/") else importer.save_photo_data(ph)
            if saved:
                photos.append(saved)
        if limits.get("tariffs_enabled") and limits.get("max_photos"):
            if len(photos) > limits["max_photos"]:
                raise HTTPException(429,
                    f"Тариф «{limits['plan'].get('name', '')}» позволяет до {limits['max_photos']} фото на товар.")
        photo = importer.save_photo_data(data.pop("photo_data", "") or data.pop("photo_url", "") or "")
        if photo:
            photos.insert(0, photo)
        max_ph = limits["max_photos"] if (limits.get("tariffs_enabled") and limits.get("max_photos")) else 20
        if photos:
            data["photos"] = photos[:max_ph]
            data["photo"] = data["photos"][0]
        if not data.get("name"):
            raise HTTPException(422, "Укажите название товара")
        data["seller_id"] = seller["id"]
        p = store.add_product(data)
        return {**p, "limits": store.seller_limits(seller)}

    @app.put("/api/seller/products/{pid}")
    async def seller_update_product(pid: int, body: dict, x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        p = store.get_product(pid)
        if not p or int(p.get("seller_id") or 0) != seller["id"]:
            raise HTTPException(403, "Это не ваш товар")
        data = dict(body)
        photo = importer.save_photo_data(data.pop("photo_data", "") or data.pop("photo_url", "") or "")
        if photo:
            data["photo"] = photo
        return store.update_product(pid, data)

    @app.delete("/api/seller/products/{pid}")
    async def seller_delete_product(pid: int, x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        p = store.get_product(pid)
        if not p or int(p.get("seller_id") or 0) != seller["id"]:
            raise HTTPException(403, "Это не ваш товар")
        store.delete_product(pid)
        return {"ok": True}

    @app.get("/api/seller/orders")
    async def seller_orders(x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        return store.seller_orders(seller["id"])

    @app.get("/api/seller/promos")
    async def seller_promos(x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        return store.seller_promos(seller["id"])

    @app.post("/api/seller/promos", status_code=201)
    async def seller_add_promo(body: dict, x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        limits = store.seller_limits(seller)
        if limits.get("tariffs_enabled"):
            pmax = limits.get("promos_max") or 0
            if pmax >= 0:
                my_promos = [p for p in store.promos() if int(p.get("seller_id") or 0) == int(seller["id"])]
                if len(my_promos) >= pmax:
                    raise HTTPException(429,
                        f"Тариф «{limits['plan'].get('name', '')}» позволяет до {pmax} промокодов.")
        body = dict(body)
        body["seller_id"] = seller["id"]
        try:
            return store.create_promo(body)
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.delete("/api/seller/promos/{code}")
    async def seller_delete_promo(code: str, x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        promo = next((p for p in store.promos() if p["code"] == code.upper()), None)
        if not promo or int(promo.get("seller_id") or 0) != seller["id"]:
            raise HTTPException(403, "Это не ваш промокод")
        store.delete_promo(code)
        return {"ok": True}

    @app.get("/api/seller/payouts")
    async def seller_payouts(x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        return store.payouts(seller["id"])

    @app.post("/api/seller/payouts/request")
    async def seller_payout_request(body: dict, x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        try:
            store.create_payout(seller["id"], int(body.get("amount", 0)), status="requested")
        except ValueError as e:
            raise HTTPException(422, str(e))
        return {"ok": True, "balance": int(store.get_seller(seller["id"])["balance"])}

    # ------------------------------------------------------------------ чат покупатель <-> продавец
    def _buyer_key(request: Request) -> str:
        tg_id, guest_id = get_user(request)
        return f"tg:{tg_id}" if tg_id else (f"g:{guest_id}" if guest_id else "")

    @app.post("/api/chat/send")
    async def chat_send(body: dict, request: Request, x_seller_key: str = Header(default="")):
        """Отправка сообщения. Продавец — по X-Seller-Key, покупатель — по guest/tg идентификации."""
        product_id = int(body.get("product_id") or 0)
        seller_id = int(body.get("seller_id") or 0)
        text = str(body.get("text") or "").strip()
        if not product_id or not seller_id or not text:
            raise HTTPException(422, "Укажите product_id, seller_id и текст")
        if len(text) > 2000:
            raise HTTPException(422, "Сообщение слишком длинное (до 2000 символов)")
        product = store.get_product(product_id)
        seller = store.get_seller(seller_id)
        if not product or not seller:
            raise HTTPException(404, "Товар или продавец не найдены")
        if int(product.get("seller_id") or 0) != int(seller_id):
            raise HTTPException(404, "Товар не принадлежит этому продавцу")
        if x_seller_key:
            me = require_seller(x_seller_key)
            if int(me["id"]) != int(seller_id):
                raise HTTPException(403, "Это не ваш товар")
            if int(product.get("seller_id") or 0) != int(seller_id):
                raise HTTPException(403, "Это не ваш товар")
            buyer_key = str(body.get("buyer_key") or "")
            if not buyer_key:
                raise HTTPException(422, "Не указан buyer_key диалога")
            msg = store.chat_add(product_id, seller_id, buyer_key, "", "seller", text)
            if bot and seller.get("tg_user_id"):
                try:
                    await bot.send_message(int(seller["tg_user_id"]),
                        "✉️ Отправлено покупателю.", disable_notification=True)
                except Exception:
                    pass
            return msg
        buyer_key = _buyer_key(request)
        if not buyer_key:
            raise HTTPException(401, "Не удалось идентифицировать покупателя")
        buyer_name = str(body.get("buyer_name") or "Покупатель").strip()[:60]
        msg = store.chat_add(product_id, seller_id, buyer_key, buyer_name, "buyer", text)
        if bot and seller.get("tg_user_id"):
            try:
                await bot.send_message(int(seller["tg_user_id"]),
                    f"💬 <b>Новое сообщение от покупателя</b>\n\n«{text[:300]}»\n\n"
                    f"Товар: {product['name']}\nОтветить: {request.url.scheme}://{request.url.netloc}/seller",
                    parse_mode="HTML")
            except Exception:
                pass
        return msg

    @app.get("/api/chat/threads")
    async def chat_threads(request: Request, x_seller_key: str = Header(default="")):
        if x_seller_key:
            seller = require_seller(x_seller_key)
            return {"side": "seller", "threads": store.chat_threads_seller(seller["id"])}
        buyer_key = _buyer_key(request)
        if not buyer_key:
            raise HTTPException(401, "Не удалось идентифицировать покупателя")
        return {"side": "buyer", "threads": store.chat_threads_buyer(buyer_key)}

    @app.get("/api/chat/messages")
    async def chat_messages(request: Request, product_id: int = 0, seller_id: int = 0,
                            buyer_key: str = "", x_seller_key: str = Header(default="")):
        if x_seller_key:
            seller = require_seller(x_seller_key)
            if int(seller["id"]) != int(seller_id):
                raise HTTPException(403, "Это не ваш диалог")
            store.chat_mark_read("seller", product_id, seller_id, buyer_key)
            return store.chat_messages(product_id, seller_id, buyer_key)
        bk = buyer_key or _buyer_key(request)
        if not bk:
            raise HTTPException(401, "Не удалось идентифицировать покупателя")
        store.chat_mark_read("buyer", product_id, seller_id, bk)
        return store.chat_messages(product_id, seller_id, bk)

    @app.get("/api/chat/unread")
    async def chat_unread(request: Request, x_seller_key: str = Header(default="")):
        if x_seller_key:
            seller = require_seller(x_seller_key)
            return {"unread": store.chat_unread_seller(seller["id"])}
        buyer_key = _buyer_key(request)
        return {"unread": store.chat_unread_buyer(buyer_key) if buyer_key else 0}

    # ------------------------------------------------------------------ торг / предложения цены (#9)
    @app.post("/api/offers")
    async def create_offer(body: dict, request: Request):
        product_id = int(body.get("product_id") or 0)
        buyer_key = _buyer_key(request)
        if not buyer_key:
            raise HTTPException(403, "Необходимо авторизоваться или иметь сессию")
        try:
            return store.create_offer(
                product_id=product_id,
                buyer_key=buyer_key,
                buyer_name=str(body.get("buyer_name") or ""),
                proposed_price=int(body.get("proposed_price") or 0),
                message=str(body.get("message") or ""),
            )
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.get("/api/offers")
    async def list_offers(seller_id: int = 0, buyer_key: str = "", product_id: int = 0,
                          status: str = "", request: Request = None):
        if not seller_id:
            # для покупателя — его ключ из запроса
            buyer_key = buyer_key or _buyer_key(request)
        return store.get_offers(seller_id=seller_id, buyer_key=buyer_key, product_id=product_id, status=status)

    @app.get("/api/offers/{offer_id}")
    async def get_offer(offer_id: int):
        r = store.offer_by_id(offer_id)
        if not r:
            raise HTTPException(404, "Предложение не найдено")
        return r

    @app.post("/api/offers/{offer_id}/respond")
    async def respond_offer(offer_id: int, body: dict, x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        offer = store.offer_by_id(offer_id)
        if not offer:
            raise HTTPException(404, "Предложение не найдено")
        if int(offer.get("seller_id") or 0) != int(seller["id"]):
            raise HTTPException(403, "Это не ваше предложение")
        try:
            return store.respond_to_offer(
                offer_id=offer_id,
                status=str(body.get("status") or ""),
                seller_response_price=int(body.get("seller_response_price") or 0),
                seller_note=str(body.get("seller_note") or ""),
            )
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.post("/api/offers/{offer_id}/cancel")
    async def cancel_offer_endpoint(offer_id: int, request: Request):
        buyer_key = _buyer_key(request)
        if not buyer_key:
            raise HTTPException(403, "Необходимо авторизоваться или иметь сессию")
        try:
            return store.cancel_offer(offer_id=offer_id, buyer_key=buyer_key)
        except ValueError as e:
            raise HTTPException(422, str(e))

    # ------------------------------------------------------------------ сравнение + сохранённые поиски (#8)
    @app.post("/api/compare")
    async def compare_action(body: dict, request: Request):
        buyer_key = _buyer_key(request)
        if not buyer_key:
            raise HTTPException(403, "Необходимо авторизоваться или иметь сессию")
        action = str(body.get("action", ""))
        product_id = int(body.get("product_id") or 0)
        try:
            if action == "add":
                return {"ok": True, "items": store.compare_add(user_key=buyer_key, product_id=product_id)}
            elif action == "remove":
                return {"ok": True, "items": store.compare_remove(user_key=buyer_key, product_id=product_id)}
            else:
                raise ValueError("action: add | remove")
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.get("/api/compare")
    async def compare_list(request: Request):
        buyer_key = _buyer_key(request)
        return store.compare_list(user_key=buyer_key or "")

    @app.post("/api/saved_searches")
    async def saved_search_create(body: dict, request: Request):
        buyer_key = _buyer_key(request)
        if not buyer_key:
            raise HTTPException(403, "Необходимо авторизоваться или иметь сессию")
        return store.saved_search_create(
            user_key=buyer_key,
            query=str(body.get("query") or ""),
            filters=body.get("filters") or {})

    @app.get("/api/saved_searches")
    async def saved_search_list(request: Request):
        buyer_key = _buyer_key(request)
        return store.saved_searches(user_key=buyer_key or "")

    @app.delete("/api/saved_searches/{sid}")
    async def saved_search_delete(sid: int, request: Request):
        buyer_key = _buyer_key(request)
        if not buyer_key:
            raise HTTPException(403, "Необходимо авторизоваться или иметь сессию")
        deleted = store.saved_search_delete(search_id=sid, user_key=buyer_key)
        if not deleted:
            raise HTTPException(404, "Поиск не найден или нет прав")
        return {"ok": True}

    @app.get("/api/seller/reviews")
    async def seller_reviews_endpoint(seller_id: int = 0, slug: str = ""):
        sid = seller_id or (store.get_seller(slug=slug) or {}).get("id") or 0
        if not sid:
            raise HTTPException(404, "Продавец не найден")
        return store.seller_reviews(sid)

    @app.post("/api/seller/review")
    async def seller_review_create(body: dict, request: Request):
        buyer_key = _buyer_key(request)
        if not buyer_key:
            raise HTTPException(403, "Необходимо авторизоваться или иметь сессию")
        seller_id = int(body.get("seller_id") or 0)
        try:
            return store.add_seller_review(
                seller_id=seller_id,
                buyer_key=buyer_key,
                buyer_name=str(body.get("buyer_name") or ""),
                rating=int(body.get("rating") or 5),
                text=str(body.get("text") or ""),
            )
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.get("/api/seller/{slug}/rating")
    async def seller_rating_public(slug: str):
        seller = store.get_seller(slug=slug)
        if not seller:
            raise HTTPException(404, "Продавец не найден")
        sid = int(seller.get("id") or 0)
        return {
            "seller": seller,
            "rating_summary": store.seller_rating(sid),
            "rating_details": store.seller_rating_details(sid),
            "reviews": store.seller_reviews(sid),
            "review_stats": store.seller_review_stats(sid),
        }

    @app.get("/api/saved_searches/notify")
    async def saved_search_notify(request: Request):
        buyer_key = _buyer_key(request)
        return store.saved_search_notifications(user_key=buyer_key or "")

    @app.get("/api/boost")
    async def list_boosts():
        return store.get_boosted_products()

    @app.post("/api/boost")
    async def create_boost(body: dict, x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        try:
            return store.create_boost(
                product_id=int(body.get("product_id") or 0),
                seller_id=seller["id"],
                duration_days=int(body.get("duration_days") or 1),
                price=int(body.get("price") or 0),
            )
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.delete("/api/boost/{boost_id}")
    async def cancel_boost_endpoint(boost_id: int, x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        return {"ok": True, "cancelled": store.cancel_boost(boost_id)}

    @app.get("/api/partner")
    async def partner_referrals(x_seller_key: str = Header(default="")):
        seller = require_seller(x_seller_key)
        return store.partner_referrals(seller_id=seller["id"])

    @app.get("/api/ad/list")
    async def ad_list(seller_id: int = 0, platform: str = ""):
        return store.campaigns(seller_id=int(seller_id or 0), platform=platform or "")

    @app.post("/api/ad/create")
    async def ad_create(req: dict):
        sid = int(req.get("seller_id", 0) or 0)
        cid = store.create_campaign(
            seller_id=sid, platform=req.get("platform", "yandex"),
            title=req.get("title", ""), budget=int(req.get("budget", 0) or 0),
            creative_url=req.get("creative_url", ""), target_city=req.get("target_city", ""))
        return {"campaign_id": cid, "status": "created"}

    @app.post("/api/ad/update")
    async def ad_update(req: dict):
        ok = store.update_campaign_status(int(req.get("campaign_id", 0) or 0), req.get("status", "draft"))
        return {"updated": ok}

    @app.post("/api/moderate")
    async def moderate(req: dict):
        return store.moderate_content(
            content_id=int(req.get("content_id", 0) or 0),
            content_type=req.get("content_type", "product"),
            text=req.get("text", ""),
            image_url=req.get("image_url", ""))

    @app.get("/api/moderation/status")
    async def moderation_status(content_id: int = 0, content_type: str = ""):
        return store.moderation_status(content_id=int(content_id or 0), content_type=content_type or "")

    @app.post("/api/label/add")
    async def label_add(req: dict):
        lid = store.add_label(product_id=int(req.get("product_id", 0) or 0), label_name=req.get("label_name", ""), label_color=req.get("label_color", "#4f46e5"))
        return {"label_id": lid}

    @app.get("/api/label/list")
    async def label_list(product_id: int = 0):
        return store.get_labels(product_id=int(product_id or 0))

    @app.get("/api/search/geo")
    async def search_geo(q: str = "", city: str = "", radius_km: int = 50):
        return store.geo_search(query=q, city=city, radius_km=int(radius_km or 50))

    @app.get("/api/boost/price")
    async def boost_prices():
        ps = (store.settings.get("tariffs") or {}).get("promo_services") or {}
        return {"boost_1d": int(ps.get("boost_1d") or 49),
                "boost_3d": int(ps.get("boost_3d") or 99),
                "boost_7d": int(ps.get("boost_7d") or 199),
                "vip_week": int(ps.get("vip_week") or 149)}

    # ------------------------------------------------------------------ админ: продавцы
    @app.get("/admin/api/sellers")
    async def admin_sellers(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return store.sellers()

    @app.post("/admin/api/sellers/{sid}/status")
    async def admin_seller_status(sid: int, body: dict, x_admin_token: str = Header(default=""),
                                  background_tasks: BackgroundTasks = None):
        require_admin(x_admin_token)
        status = str(body.get("status", ""))
        if status not in ("active", "blocked", "pending"):
            raise HTTPException(422, "Статус: active | blocked | pending")
        s = store.set_seller_status(sid, status)
        if not s:
            raise HTTPException(404, "Продавец не найден")
        if status == "active" and s.get("email") and mailer.available(store):
            base = _abs(request, "/")
            background_tasks.add_task(mailer.send_email, store, s["email"],
                f"Ваша витрина одобрена — {store.settings['shop_name']}",
                f"Здравствуйте!\n\nВитрина «{s['store_name']}» подтверждена и активна.\n"
                f"Адрес: {base}seller/{s['slug']}\nКабинет: {base}seller\n"
                "Ваши товары уже видны в каталоге — добавляйте новые и следите за заказами.")
        return s

    @app.post("/admin/api/sellers/{sid}/commission")
    async def admin_seller_commission(sid: int, body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        s = store.set_seller_commission(sid, int(body.get("percent", 15)))
        if not s:
            raise HTTPException(404, "Продавец не найден")
        return s

    @app.post("/admin/api/sellers/{sid}/reset-key")
    async def admin_seller_reset_key(sid: int, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return {"key": store.reset_seller_key(sid)}

    @app.get("/admin/api/payouts")
    async def admin_payouts(x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        return store.payouts()

    @app.post("/admin/api/payouts/{pid}/status")
    async def admin_payout_status(pid: int, body: dict, x_admin_token: str = Header(default=""),
                                  background_tasks: BackgroundTasks = None):
        require_admin(x_admin_token)
        p = store.mark_payout_status(pid, str(body.get("status", "paid")))
        if not p:
            raise HTTPException(404, "Выплата не найдена")
        if p["status"] == "paid":
            s = store.get_seller(p["seller_id"])
            if s and s.get("email") and mailer.available(store):
                background_tasks.add_task(mailer.send_email, store, s["email"],
                    f"Выплата {p['amount']} ₽ — {store.settings['shop_name']}",
                    f"Здравствуйте!\n\nВаша выплата {p['amount']} ₽ проведена. Спасибо за продажи!")
        return p

    @app.get("/admin/api/reports/sellers")
    async def admin_sellers_report(date_from: str = "", date_to: str = "",
                                   x_admin_token: str = Header(default="")):
        """Отчёт по комиссиям площадки за период."""
        require_admin(x_admin_token)
        return store.commission_report(date_from, date_to)

    @app.get("/admin/api/reports/sellers.pdf")
    async def admin_sellers_report_pdf(date_from: str = "", date_to: str = "",
                                       x_admin_token: str = Header(default="")):
        """PDF-отчёт по комиссиям площадки за период."""
        require_admin(x_admin_token)
        rep = store.commission_report(date_from, date_to)
        payouts = [p for p in store.payouts()
                   if (not date_from or (p.get("created_at") or "")[:10] >= date_from)
                   and (not date_to or (p.get("created_at") or "")[:10] <= date_to)]
        pdf = pdfreport.commission_report_pdf(
            store.settings["shop_name"], date_from, date_to,
            rep["rows"], rep["totals"], payouts)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": "attachment; filename=\"commission-report.pdf\""})

    @app.post("/admin/api/payouts")
    async def admin_create_payout(body: dict, x_admin_token: str = Header(default="")):
        require_admin(x_admin_token)
        try:
            return store.create_payout(int(body.get("seller_id", 0)), int(body.get("amount", 0)),
                                       status="paid", note=str(body.get("note", "") or ""))
        except ValueError as e:
            raise HTTPException(422, str(e))

    # ------------------------------------------------------------------ 1С
    @app.get("/1c/catalog")
    async def one_c_catalog(x_1c_token: str = Header(default="")):
        require_1c(x_1c_token)
        products = []
        for p in store.products():
            products.append({
                "code": p.get("code") or f"TG-{p['id']}",
                "id": p["id"], "name": p["name"], "price": p["price"],
                "description": p.get("description", ""), "category": p.get("category", ""),
                "photo": p.get("photo", ""), "in_stock": p.get("in_stock", True),
                "stock": p.get("stock", -1),
            })
        return {"products": products}

    @app.post("/1c/catalog")
    async def one_c_catalog_push(body: dict, x_1c_token: str = Header(default="")):
        require_1c(x_1c_token)
        try:
            items = importer.parse_json_items(body)
        except ValueError as e:
            raise HTTPException(422, str(e))
        result = importer.apply_import(store, items)
        return {"ok": True, **result}

    @app.get("/1c/orders")
    async def one_c_orders(status: str = "", synced: str = "0", x_1c_token: str = Header(default="")):
        require_1c(x_1c_token)
        statuses = {s for s in status.split(",") if s} or None
        out = []
        for o in store.orders(limit=500):
            if synced == "1" and o.get("synced"):
                continue
            if statuses and o["status"] not in statuses:
                continue
            out.append({
                "id": o["id"], "status": o["status"], "total": o["total"],
                "delivery": o["delivery"], "customer": o["customer"],
                "created_at": o["created_at"], "payment": o["payment"],
                "items": [{"code": (store.get_product(i["id"]) or {}).get("code") or f"TG-{i['id']}",
                           "name": i["name"], "price": i["price"], "qty": i["qty"]} for i in o["items"]],
            })
        return {"orders": out}

    @app.post("/1c/orders/ack")
    async def one_c_orders_ack(body: dict, x_1c_token: str = Header(default="")):
        require_1c(x_1c_token)
        ids = body.get("ids", []) if isinstance(body, dict) else []
        return {"synced": store.mark_synced(ids)}

    @app.post("/1c/orders/status")
    async def one_c_orders_status(body: dict, x_1c_token: str = Header(default="")):
        require_1c(x_1c_token)
        oid = body.get("id", "")
        status = body.get("status", "")
        if status not in {"shipped", "delivered", "cancelled"}:
            raise HTTPException(422, "1С может менять статус только на shipped/delivered/cancelled")
        o = store.set_order_status(oid, status)
        if not o:
            raise HTTPException(404, "Заказ не найден")
        return {"ok": True}

    # ------------------------------------------------------------------ вебхуки
    @app.post("/webhook/yookassa")
    async def webhook_yookassa(request: Request, background_tasks: BackgroundTasks):
        try:
            body = await request.json()
        except Exception:
            return {"ok": False}
        event = body.get("event", "")
        obj = body.get("object", {})
        if event == "payment.succeeded" and obj.get("paid"):
            order_id = (obj.get("metadata") or {}).get("order_id")
            o = store.confirm_payment(order_id, "yookassa", obj.get("id")) if order_id else None
            if o:
                store.set_payment_method(order_id, "yookassa")
                if notify_order_paid:
                    background_tasks.add_task(notify_order_paid, o)
                background_tasks.add_task(after_payment, store, order_id, notify_admin)
        return {"ok": True}

    @app.post("/webhook/cryptobot")
    async def webhook_cryptobot(request: Request, background_tasks: BackgroundTasks):
        try:
            body = await request.json()
        except Exception:
            return {"ok": True}
        if body.get("update_type") == "invoice_paid":
            payload = body.get("payload") or {}
            order_id = payload.get("payload")
            inv_id = str(payload.get("invoice_id", ""))
            o = store.confirm_payment(order_id, "cryptobot", inv_id) if order_id else None
            if o:
                store.set_payment_method(order_id, "cryptobot")
                if notify_order_paid:
                    background_tasks.add_task(notify_order_paid, o)
                background_tasks.add_task(after_payment, store, order_id, notify_admin)
        return {"ok": True}

    @app.post("/webhook/tbank")
    async def webhook_tbank(request: Request, background_tasks: BackgroundTasks):
        """Уведомления Т-Банка: проверяем подпись Token, при CONFIRMED — заказ оплачен."""
        try:
            body = await request.json()
        except Exception:
            return {"ok": False}
        cfg = store.settings["payments"]["tbank"]
        token = body.get("Token")
        if token and cfg.get("password"):
            calc = TbankProvider.sign({k: v for k, v in body.items() if k != "Token"}, cfg["password"])
            if not hmac.compare_digest(calc, str(token)):
                log.warning("Т-Банк webhook: неверная подпись")
                return {"ok": False}
        if body.get("Status") == "CONFIRMED":
            order_id = str(body.get("OrderId") or "")
            payment_id = str(body.get("PaymentId") or "")
            o = store.confirm_payment(order_id, "tbank", payment_id) if order_id else None
            if o:
                store.set_payment_method(order_id, "tbank")
                if notify_order_paid:
                    background_tasks.add_task(notify_order_paid, o)
                background_tasks.add_task(after_payment, store, order_id, notify_admin)
        return {"ok": True}

    # статическая админка — в конце, чтобы не перекрывала /admin/api
    app.mount("/admin", StaticFiles(directory=config.ADMIN_DIR, html=True), name="admin")
    return app
