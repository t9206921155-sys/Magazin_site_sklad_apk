"""Клиент Avito.ru: выкладывание товаров магазина на Avito.

Два канала:
1) REST API (api.avito.ru): создание/обновление/закрытие объявлений.
   Требуется заявка на доступ к API в кабинете Avito → client_id + client_secret.
2) Автозагрузка (XML-фид): /avito/autoload.xml?key=... — ссылка добавляется
   в Avito как источник автозагрузки, Avito сам забирает каталог по расписанию.
   Не требует API-заявки, нужен только аккаунт Avito с включённой автозагрузкой.

Фотографии: Avito скачивает изображения по URL, поэтому нужен публичный WEBAPP_URL;
если его нет — после создания объявления фото загружаются напрямую multipart-запросом.
"""
import logging
import re
import time
import xml.sax.saxutils as sax

import requests

import config

log = logging.getLogger("shop.avito")

API = "https://api.avito.ru"

_token_cache = {"token": None, "ts": 0, "key": None}


def _cfg(store) -> dict:
    return store.settings.get("avito") or {}


def public_base() -> str:
    return config.WEBAPP_URL or ""


def absolute_image_url(photo: str, base: str) -> str:
    if not photo:
        return ""
    if photo.startswith("http"):
        return photo
    return (base or "").rstrip("/") + photo


class AvitoClient:
    def __init__(self, settings: dict):
        cfg = settings.get("avito") or {}
        self.client_id = (cfg.get("client_id") or "").strip()
        self.client_secret = (cfg.get("client_secret") or "").strip()
        self.category_id = int(cfg.get("category_id") or 0)
        self.goods_type = (cfg.get("goods_type") or "Новое").strip()
        self.ad_type = (cfg.get("ad_type") or "Товар от производителя").strip()
        self.contact_phone = (cfg.get("contact_phone") or "").strip()
        self.address = (cfg.get("address") or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret)

    # ------------------------------------------------------------------ auth
    def _token(self) -> str:
        if not self.enabled:
            raise ValueError("Avito не настроен: укажите client_id и client_secret в админке")
        key = self.client_id
        if _token_cache["token"] and _token_cache["key"] == key and time.time() - _token_cache["ts"] < 3500:
            return _token_cache["token"]
        r = requests.post(
            f"{API}/token/",
            params={"grant_type": "client_credentials", "client_id": self.client_id,
                    "client_secret": self.client_secret}, timeout=30)
        data = r.json()
        if r.status_code >= 400 or not data.get("access_token"):
            err = (data.get("error") or data.get("message") or r.status_code)
            raise ValueError(f"Avito: ошибка авторизации ({err}). Проверьте client_id/client_secret "
                             "и заявку на доступ к API в кабинете Avito.")
        _token_cache.update(token=data["access_token"], ts=time.time(), key=key)
        return data["access_token"]

    def _headers(self, extra=None) -> dict:
        h = {"Authorization": "Bearer " + self._token()}
        if extra:
            h.update(extra)
        return h

    def _api(self, method: str, path: str, **kwargs) -> dict:
        r = requests.request(method, API + path, headers=self._headers(kwargs.pop("headers", None)),
                             timeout=60, **kwargs)
        if r.status_code >= 400:
            try:
                err = r.json().get("error", {})
                if isinstance(err, dict):
                    msg = err.get("message") or err.get("code")
                else:
                    msg = err
            except ValueError:
                msg = r.text[:200]
            raise ValueError(f"Avito API {path}: {r.status_code} {msg}")
        if r.status_code == 204 or not r.content:
            return {}
        try:
            return r.json()
        except ValueError:
            return {}

    # ------------------------------------------------------------------ методы
    def categories(self) -> list:
        data = self._api("GET", "/core/v1/categories")
        out = []
        for c in data if isinstance(data, list) else data.get("categories", []):
            out.append({"id": c.get("id"), "name": c.get("name", "")})
        return out

    def _body(self, product: dict, image_urls: list = None) -> dict:
        body = {
            "category_id": self.category_id or None,
            "title": (product["name"] or "")[:100],
            "description": ((product.get("description") or "") + "\n\nАртикул: "
                           + (product.get("code") or f"TG-{product['id']}"))[:6000],
            "price": int(product["price"]),
            "goods_type": self.goods_type,
            "ad_type": self.ad_type,
        }
        if self.address:
            body["address"] = self.address
        if self.contact_phone:
            body["contacts"] = [{"phone": self.contact_phone}]
        if image_urls:
            body["images"] = [{"url": u} for u in image_urls if u]
        return {k: v for k, v in body.items() if v is not None}

    def create_item(self, product: dict, image_urls: list = None) -> str:
        data = self._api("POST", "/core/v1/items", json=self._body(product, image_urls))
        item_id = data.get("id") or data.get("item_id")
        if not item_id:
            raise ValueError("Avito не вернул ID объявления: " + str(data)[:200])
        return str(item_id)

    def update_item(self, item_id: str, product: dict, image_urls: list = None) -> dict:
        return self._api("PUT", f"/core/v1/items/{item_id}", json=self._body(product, image_urls))

    def upload_image(self, item_id: str, file_path: str) -> dict:
        with open(file_path, "rb") as f:
            return self._api("POST", f"/core/v1/items/{item_id}/images",
                             files={"uploadfile[]": (file_path.rsplit("/", 1)[-1], f, "image/jpeg")},
                             headers={"Content-Type": "multipart/form-data"})

    def activate(self, item_id: str) -> dict:
        return self._api("POST", f"/core/v1/items/{item_id}/activate")

    def close_item(self, item_id: str) -> dict:
        return self._api("POST", f"/core/v1/items/{item_id}/close")

    def get_item(self, item_id: str) -> dict:
        return self._api("GET", f"/core/v1/items/{item_id}")


# ---------------------------------------------------------------- выкладка товара
def local_photo_path(photo: str) -> str:
    if photo.startswith("/webapp/"):
        import os
        return os.path.join(config.WEBAPP_DIR, photo.split("/webapp/", 1)[1])
    return ""


def post_to_avito(store, product: dict) -> dict:
    """Создаёт или обновляет объявление Avito для товара."""
    cfg = _cfg(store)
    client = AvitoClient(store.settings)
    if not client.enabled:
        return {"ok": False, "error": "Avito не настроен (админка → Настройки → Avito)"}
    if not client.category_id:
        return {"ok": False, "error": "Не указана категория Avito (category_id)"}

    base = public_base()
    image_urls = []
    if base and product.get("photo"):
        image_urls = [absolute_image_url(product["photo"], base)]

    existing = (product.get("avito_item_id") or "").strip()
    try:
        if existing:
            client.update_item(existing, product, image_urls or None)
            item_id = existing
        else:
            item_id = client.create_item(product, image_urls or None)

        # фото напрямую, если нет публичного URL
        if not image_urls:
            path = local_photo_path(product.get("photo") or "")
            if path:
                try:
                    client.upload_image(item_id, path)
                except Exception as e:
                    log.warning("Avito: не удалось загрузить фото %s: %s", item_id, e)

        try:
            client.activate(item_id)
            status = "active"
        except Exception as e:
            log.warning("Avito: активация %s: %s", item_id, e)
            status = "created"

        url = f"https://www.avito.ru/{item_id}"
        store.set_avito(product["id"], item_id, url, status)
        return {"ok": True, "item_id": item_id, "url": url, "status": status}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        log.warning("Avito: %s", e)
        return {"ok": False, "error": str(e)[:300]}


def close_on_avito(store, product: dict) -> dict:
    cfg = _cfg(store)
    client = AvitoClient(store.settings)
    item_id = (product.get("avito_item_id") or "").strip()
    if not item_id:
        return {"ok": False, "error": "У товара нет объявления на Avito"}
    try:
        client.close_item(item_id)
        store.set_avito(product["id"], item_id, product.get("avito_url", ""), "closed")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


# ---------------------------------------------------------------- XML-фид автозагрузки
def build_autoload_xml(store) -> str:
    """XML-фид автозагрузки Avito (target=Avito.ru, formatVersion=3)."""
    cfg = _cfg(store)
    base = public_base()
    shop = store.settings["shop_name"]
    contact = (cfg.get("contact_phone") or "").strip()
    address = (cfg.get("address") or "").strip()
    category_name = (cfg.get("category_name") or "Товары").strip()

    rows = []
    for p in store.products():
        if not p.get("in_stock"):
            continue
        img = absolute_image_url(p.get("photo") or "", base) if base else ""
        code = sax.escape(str(p.get("code") or f"TG-{p['id']}"))
        rows.append(
            "    <Ad>\n"
            f"      <Id>{code}</Id>\n"
            f"      <Category>{sax.escape(category_name)}</Category>\n"
            f"      <GoodsType>{sax.escape(cfg.get('goods_type') or 'Новое')}</GoodsType>\n"
            f"      <AdType>{sax.escape(cfg.get('ad_type') or 'Товар от производителя')}</AdType>\n"
            f"      <Title>{sax.escape(p['name'][:100])}</Title>\n"
            f"      <Description>{sax.escape(((p.get('description') or '') + ' Артикул: ' + str(p.get('code') or p['id']))[:6000])}</Description>\n"
            f"      <Price>{int(p['price'])}</Price>\n"
            + (f"      <Images><Image url=\"{sax.escape(img)}\"/></Images>\n" if img else "")
            + (f"      <ContactPhone>{sax.escape(contact)}</ContactPhone>\n" if contact else "")
            + (f"      <Address>{sax.escape(address)}</Address>\n" if address else "")
            + "      <ContactMethod>Сообщения</ContactMethod>\n"
            "    </Ad>\n")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Ads target="Avito.ru" formatVersion="3">\n' + "".join(rows) + "</Ads>\n")
