"""Облачное хранилище: Supabase (или совместимый REST-бэкенд).

Важно: основной сервер магазина УЖЕ является единой облачной базой — все устройства
работают с ним напрямую, фото хранятся на нём. Supabase здесь — дополнительный слой:

  • хостинг фото в Storage (CDN, публичные URL);
  • резервная копия каталога в таблице products (upsert по id);
  • опционально: внешний источник для интеграций.

Все настройки — в приложении «Склад» (⚙️ Настройки → Облако).
Клиент работает по REST (requests) — без SDK, ничего доустанавливать не нужно.
"""
import json
import logging
import os

import requests

import config

log = logging.getLogger("shop.cloud")


class SupabaseClient:
    def __init__(self, url: str, key: str, bucket: str = "shop-photos"):
        self.url = (url or "").rstrip("/")
        self.key = key
        self.bucket = bucket or "shop-photos"

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.key)

    def _h(self, extra=None) -> dict:
        h = {"apikey": self.key, "Authorization": "Bearer " + self.key}
        if extra:
            h.update(extra)
        return h

    def ping(self) -> dict:
        if not self.enabled:
            return {"ok": False, "error": "Не заданы URL и ключ"}
        try:
            r = requests.get(f"{self.url}/rest/v1/", headers=self._h(), timeout=15)
            return {"ok": True, "status": r.status_code}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def public_url(self, fname: str) -> str:
        return f"{self.url}/storage/v1/object/public/{self.bucket}/{fname}"

    def upload_photo(self, local_path: str) -> dict:
        """Загружает файл фото в bucket. Возвращает {ok, url|error}."""
        try:
            fname = os.path.basename(local_path)
            with open(local_path, "rb") as f:
                r = requests.post(
                    f"{self.url}/storage/v1/object/{self.bucket}/{fname}",
                    headers={**self._h(), "Content-Type": "image/jpeg", "x-upsert": "true"},
                    data=f.read(), timeout=60)
            if r.status_code >= 300:
                return {"ok": False, "error": f"{r.status_code}: {r.text[:120]}"}
            return {"ok": True, "url": self.public_url(fname)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def push_products(self, products: list) -> dict:
        try:
            r = requests.post(f"{self.url}/rest/v1/products", json=products,
                              headers={**self._h(), "Prefer": "resolution=merge-duplicates"},
                              timeout=90)
            if r.status_code >= 300:
                return {"ok": False, "error": f"{r.status_code}: {r.text[:150]}"}
            return {"ok": True, "count": len(products)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def pull_products(self) -> dict:
        try:
            r = requests.get(f"{self.url}/rest/v1/products?select=*",
                             headers={**self._h(), "Accept": "application/json"}, timeout=60)
            if r.status_code >= 300:
                return {"ok": False, "error": f"{r.status_code}: {r.text[:150]}"}
            return {"ok": True, "products": r.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}


def _client(store) -> SupabaseClient:
    c = store.settings.get("cloud") or {}
    return SupabaseClient(c.get("url", ""), c.get("key", ""), c.get("bucket", "shop-photos"))


def local_photo_path(photo: str) -> str:
    if photo and str(photo).startswith("/webapp/"):
        return os.path.join(config.WEBAPP_DIR, str(photo).split("/webapp/", 1)[1])
    return ""


def sync_to_cloud(store) -> dict:
    """Синхронизация в облако: каталог (upsert) + все фото. Провайдер: s3 | supabase | mysql.
    Сохраняет cloud_state (маппинг фото local->URL) — дальше фото подтягиваются с CDN."""
    import datetime as _dt
    provider, client = _clients(store)
    if not client.enabled:
        return {"ok": False, "error": "Облако не настроено (нет ключей)"}
    photos = {"uploaded": 0, "errors": 0}
    photo_map = dict((store.settings.get("cloud_state") or {}).get("photos") or {})
    photo_client = _photo_client(store, provider, client)
    for p in store.products():
        for ph in [p.get("photo")] + p.get("photos", []):
            lp = local_photo_path(ph)
            if not lp or not os.path.exists(lp):
                continue
            if str(ph) in photo_map and photo_map[str(ph)]:
                continue  # уже в облаке
            if photo_client is None:
                continue  # mysql без S3 — фото не хостятся в MySQL
            res = photo_client.upload_photo(lp)
            if res.get("ok"):
                photo_map[str(ph)] = res["url"]
                photos["uploaded"] += 1
            else:
                photos["errors"] += 1
                log.warning("облако: %s -> %s", lp, res.get("error"))
    prods = [_product_record(p) for p in store.products()]
    products_res = client.push_products(prods)
    if products_res.get("ok"):
        store.set_cloud_state({
            "provider": provider, "photos": photo_map,
            "last_sync": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "catalog_count": len(prods),
        })
    return {"ok": products_res.get("ok", False),
            "products": products_res.get("count", 0) if products_res.get("ok") else 0,
            "photos": photos,
            "error": products_res.get("error") or ""}


def test_cloud(store) -> dict:
    provider, client = _clients(store)
    return {**client.ping(), "provider": provider}


# Пресеты российских S3-провайдеров: endpoint, регион и подсказка, где взять ключи.
# Endpoint/регион можно переопределить вручную (поле «Другой S3» или свои значения).
S3_PRESETS = {
    "selectel": {
        "label": "Selectel — Объектное хранилище",
        "endpoint": "https://s3.storage.selcloud.ru",
        "region": "ru-1",
        "hint": "Ключи: ЛК Selectel → Объектное хранилище → S3-ключи. Регионы: ru-1 (СПб), ru-2 (Москва), ru-3.",
    },
    "cloudru": {
        "label": "Cloud.ru — Object Storage (SberCloud)",
        "endpoint": "https://obs.ru-moscow-1.hc.sbercloud.ru",
        "region": "ru-moscow-1",
        "hint": "Ключи: ЛК cloud.ru → Object Storage → Access Key/Secret Key. Endpoint зависит от региона — сверьте с документацией.",
    },
    "vk": {
        "label": "VK Cloud — Объектное хранилище",
        "endpoint": "https://hb.bizmrg.com",
        "region": "ru-msk",
        "hint": "Ключи: ЛК VK Cloud → Объектное хранилище → Аккаунты доступа (Access Key ID / Secret).",
    },
    "yandex": {
        "label": "Яндекс — Объектное хранилище",
        "endpoint": "https://storage.yandexcloud.net",
        "region": "ru-central1",
        "hint": "Ключи: Яндекс.Облако → Сервисные аккаунты → Статические ключи доступа (AWS-совместимые).",
    },
    "minio": {
        "label": "MinIO (свой сервер)",
        "endpoint": "",
        "region": "us-east-1",
        "hint": "Укажите endpoint своего MinIO (https://minio.example.com) и ключи из консоли MinIO.",
    },
    "custom": {
        "label": "Другой S3-совместимый",
        "endpoint": "",
        "region": "ru-1",
        "hint": "Укажите endpoint, ключи и регион вручную.",
    },
}


def s3_presets() -> list:
    return [{"id": k, **v} for k, v in S3_PRESETS.items()]


def apply_s3_preset(cloud: dict) -> dict:
    """Подставляет endpoint/регион из выбранного пресета, если они не заданы вручную."""
    c = dict(cloud or {})
    p = S3_PRESETS.get(c.get("s3_preset") or "selectel", S3_PRESETS["custom"])
    c["s3_endpoint"] = c.get("s3_endpoint") or p["endpoint"]
    c["s3_region"] = c.get("s3_region") or p["region"]
    return c


class S3Client:
    """S3-совместимое объектное хранилище (Selectel, Cloud.ru, VK Cloud, Яндекс, MinIO).
    Идеально для фото объявлений: дёшево, CDN, публичные URL. Работает через boto3."""

    def __init__(self, endpoint: str, access_key: str, secret_key: str,
                 bucket: str, region: str = "ru-1"):
        self.endpoint = (endpoint or "").rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket or "shop-photos"
        self.region = region or "ru-1"

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint and self.access_key and self.secret_key)

    def _client(self):
        try:
            import boto3
        except ImportError:
            raise ValueError("Не установлен boto3: pip install boto3")
        return boto3.client(
            "s3", endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region)

    def ping(self) -> dict:
        if not self.enabled:
            return {"ok": False, "error": "Не заданы endpoint/ключи S3"}
        try:
            self._client().head_bucket(Bucket=self.bucket)
            return {"ok": True, "status": 200}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def public_url(self, fname: str) -> str:
        return f"{self.endpoint}/{self.bucket}/{fname}"

    def upload_photo(self, local_path: str) -> dict:
        try:
            import boto3
            fname = os.path.basename(local_path)
            self._client().upload_file(local_path, self.bucket, fname,
                                       ExtraArgs={"ContentType": "image/jpeg", "ACL": "public-read"})
            return {"ok": True, "url": self.public_url(fname)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def push_products(self, products: list) -> dict:
        try:
            import json as _json
            body = _json.dumps(products, ensure_ascii=False).encode("utf-8")
            self._client().put_object(Bucket=self.bucket, Key="catalog/products.json",
                                      Body=body, ContentType="application/json", ACL="public-read")
            return {"ok": True, "count": len(products)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}


def _clients(store) -> tuple:
    """Возвращает (провайдер, клиент): s3 | supabase | mysql."""
    c = store.settings.get("cloud") or {}
    provider = c.get("provider") or "s3"
    if provider == "s3":
        c2 = apply_s3_preset(c)
        return provider, S3Client(c2.get("s3_endpoint", ""), c2.get("s3_access_key", ""),
                                  c2.get("s3_secret_key", ""), c2.get("bucket", "shop-photos"),
                                  c2.get("s3_region", "ru-1"))
    if provider == "mysql":
        return provider, MySQLClient(c.get("mysql_host", ""), c.get("mysql_port", 3306),
                                     c.get("mysql_user", ""), c.get("mysql_password", ""),
                                     c.get("mysql_database", ""), c.get("mysql_table", "products"))
    return provider, SupabaseClient(c.get("url", ""), c.get("key", ""), c.get("bucket", "shop-photos"))


def _product_record(p: dict) -> dict:
    return {
        "id": p["id"], "code": p.get("code", ""), "name": p["name"],
        "category": p.get("category", ""), "price": p["price"],
        "old_price": p.get("old_price", 0), "stock": p.get("stock", -1),
        "description": p.get("description", ""), "photo": p.get("photo", ""),
        "photos": p.get("photos", []), "storage_location": p.get("storage_location", ""),
        "owner_name": p.get("owner_name", ""), "barcode": p.get("barcode", ""),
        "on_showcase": p.get("on_showcase", True), "in_stock": p.get("in_stock", True),
    }


def _photo_client(store, provider, main_client):
    """Клиент для загрузки фото: для mysql фото кладутся в S3-бакет (если задан),
    иначе — в сам клиент (s3/supabase)."""
    if provider == "mysql":
        c = apply_s3_preset(store.settings.get("cloud") or {})
        s3 = S3Client(c.get("s3_endpoint", ""), c.get("s3_access_key", ""),
                      c.get("s3_secret_key", ""), c.get("bucket", "shop-photos"),
                      c.get("s3_region", "ru-1"))
        return s3 if s3.enabled else None
    return main_client if hasattr(main_client, "upload_photo") else None


def resolve_photo_url(store, photo: str) -> str:
    """Подтягивание фото с облака: если облако включено и use_cdn, отдаём CDN-URL
    из состояния последней синхронизации; иначе — локальный путь (fallback)."""
    if not photo:
        return photo
    c = store.settings.get("cloud") or {}
    st = store.settings.get("cloud_state") or {}
    if c.get("enabled") and c.get("use_cdn", True) and st.get("provider") == c.get("provider"):
        url = (st.get("photos") or {}).get(str(photo))
        if url:
            return url
    return photo


def sync_one_product(store, product: dict) -> dict:
    """Автосинхронизация одного товара (после сохранения): фото + строка каталога."""
    provider, client = _clients(store)
    if not client.enabled:
        return {"ok": False, "error": "Облако не настроено"}
    photos_map = dict((store.settings.get("cloud_state") or {}).get("photos") or {})
    photo_client = _photo_client(store, provider, client)
    for ph in [product.get("photo")] + list(product.get("photos") or []):
        lp = local_photo_path(ph)
        if not lp or not os.path.exists(lp) or photo_client is None:
            continue
        res = photo_client.upload_photo(lp)
        if res.get("ok"):
            photos_map[str(ph)] = res["url"]
    pres = client.push_products([_product_record(product)])
    if pres.get("ok"):
        st = (store.settings.get("cloud_state") or {})
        store.set_cloud_state({**st, "provider": provider, "photos": photos_map,
                               "last_sync": __import__("datetime").datetime.now(
                                   __import__("datetime").timezone.utc).isoformat()})
    return {"ok": pres.get("ok"), "photos": len(photos_map), "error": pres.get("error") or ""}


def restore_from_cloud(store) -> dict:
    """Восстановление каталога из облака (pull) — обновляет/создаёт товары локально."""
    provider, client = _clients(store)
    if not client.enabled:
        return {"ok": False, "error": "Облако не настроено"}
    res = client.pull_products()
    if not res.get("ok"):
        return res
    created = updated = 0
    for rec in res["products"]:
        rec_id = int(rec.get("id") or 0)
        existing = store.get_product(rec_id) if rec_id else None
        data = {k: rec.get(k) for k in ("code", "name", "category", "price", "old_price",
                                        "stock", "description", "photo", "photos",
                                        "storage_location", "owner_name", "barcode",
                                        "on_showcase", "in_stock")}
        if existing:
            store.update_product(rec_id, data)
            updated += 1
        else:
            store.add_product({**data, "id": None, "name": rec.get("name") or "Товар из облака"})
            created += 1
    return {"ok": True, "created": created, "updated": updated}
