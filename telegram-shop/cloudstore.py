"""Облачное хранилище для склада.

Базовый рабочий сценарий проекта:
- живая база склада и админки живёт на VPS в SQLite (`data/shop.db`);
- облако используется для фото, CDN-URL и резервных копий;
- APK и веб-склад работают с API сервера на VPS, а не с объектным хранилищем напрямую.

Поддерживаются провайдеры:
- s3       — S3-совместимое хранилище (Selectel / Cloud.ru / VK Cloud / Yandex / MinIO)
- supabase — Storage + REST-таблица products
- mysql    — внешний каталог в MySQL / MariaDB (фото при этом всё равно можно класть в S3)
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from urllib.parse import quote

import requests

import config

log = logging.getLogger("shop.cloud")


def _join_key(*parts) -> str:
    chunks = []
    for part in parts:
        if part is None:
            continue
        text = str(part).strip().strip("/")
        if text:
            chunks.append(text)
    return "/".join(chunks)


def _s3_http_url(endpoint: str, bucket: str, key: str) -> str:
    base = (endpoint or "").rstrip("/")
    key = quote(str(key).lstrip("/"), safe="/-_.~")
    return f"{base}/{quote(str(bucket), safe='-_.~')}/{key}"


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
        try:
            fname = os.path.basename(local_path)
            with open(local_path, "rb") as f:
                r = requests.post(
                    f"{self.url}/storage/v1/object/{self.bucket}/{fname}",
                    headers={**self._h(), "Content-Type": "image/jpeg", "x-upsert": "true"},
                    data=f.read(), timeout=60)
            if r.status_code >= 300:
                return {"ok": False, "error": f"{r.status_code}: {r.text[:120]}"}
            return {"ok": True, "url": self.public_url(fname), "key": fname}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def push_products(self, products: list) -> dict:
        try:
            r = requests.post(
                f"{self.url}/rest/v1/products",
                json=products,
                headers={**self._h(), "Prefer": "resolution=merge-duplicates"},
                timeout=90,
            )
            if r.status_code >= 300:
                return {"ok": False, "error": f"{r.status_code}: {r.text[:150]}"}
            return {"ok": True, "count": len(products)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def pull_products(self) -> dict:
        try:
            r = requests.get(
                f"{self.url}/rest/v1/products?select=*",
                headers={**self._h(), "Accept": "application/json"},
                timeout=60,
            )
            if r.status_code >= 300:
                return {"ok": False, "error": f"{r.status_code}: {r.text[:150]}"}
            return {"ok": True, "products": r.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}


# Пресеты российских S3-провайдеров: endpoint, регион и подсказка, где взять ключи.
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
        "hint": "Ключи: Яндекс Облако → Сервисные аккаунты → Статические ключи доступа (AWS-совместимые).",
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
    c = dict(cloud or {})
    preset = S3_PRESETS.get(c.get("s3_preset") or "yandex", S3_PRESETS["custom"])
    c["s3_endpoint"] = c.get("s3_endpoint") or preset["endpoint"]
    c["s3_region"] = c.get("s3_region") or preset["region"]
    c["photo_prefix"] = str(c.get("photo_prefix") or "products").strip().strip("/")
    c["catalog_prefix"] = str(c.get("catalog_prefix") or "catalog").strip().strip("/")
    c["backup_prefix"] = str(c.get("backup_prefix") or "sqlite").strip().strip("/")
    c["backup_bucket"] = str(c.get("backup_bucket") or "shop-backups").strip()
    return c


class S3Client:
    """S3-совместимое объектное хранилище.

    Используется для:
    - публичных фото товаров (`photo_prefix`);
    - публичного JSON-каталога (`catalog_prefix/products.json`);
    - приватных резервных копий SQLite (`backup_bucket` + `backup_prefix`).
    """

    def __init__(self, endpoint: str, access_key: str, secret_key: str,
                 bucket: str, region: str = "ru-central1",
                 photo_prefix: str = "products", catalog_prefix: str = "catalog"):
        self.endpoint = (endpoint or "").rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket or "shop-photos"
        self.region = region or "ru-central1"
        self.photo_prefix = (photo_prefix or "").strip().strip("/")
        self.catalog_prefix = (catalog_prefix or "").strip().strip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint and self.access_key and self.secret_key and self.bucket)

    def _client(self):
        try:
            import boto3
        except ImportError:
            raise ValueError("Не установлен boto3: pip install boto3")
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
        )

    def ping(self) -> dict:
        if not self.enabled:
            return {"ok": False, "error": "Не заданы endpoint/ключи S3"}
        try:
            self._client().head_bucket(Bucket=self.bucket)
            return {"ok": True, "status": 200}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def public_url_for_key(self, key: str) -> str:
        return _s3_http_url(self.endpoint, self.bucket, key)

    def photo_key(self, fname: str) -> str:
        return _join_key(self.photo_prefix, os.path.basename(fname))

    def catalog_key(self) -> str:
        return _join_key(self.catalog_prefix, "products.json")

    def public_url(self, fname: str) -> str:
        return self.public_url_for_key(self.photo_key(fname))

    def upload_bytes(self, data: bytes, key: str, content_type: str = "application/octet-stream",
                     public: bool = False) -> dict:
        try:
            extra = {"ContentType": content_type}
            if public:
                extra["ACL"] = "public-read"
            self._client().put_object(Bucket=self.bucket, Key=key, Body=data, **extra)
            return {
                "ok": True,
                "bucket": self.bucket,
                "key": key,
                "url": self.public_url_for_key(key) if public else "",
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def upload_file(self, local_path: str, key: str, content_type: str = "application/octet-stream",
                    public: bool = False) -> dict:
        try:
            extra = {"ContentType": content_type}
            if public:
                extra["ACL"] = "public-read"
            self._client().upload_file(local_path, self.bucket, key, ExtraArgs=extra)
            return {
                "ok": True,
                "bucket": self.bucket,
                "key": key,
                "url": self.public_url_for_key(key) if public else "",
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def upload_photo(self, local_path: str) -> dict:
        key = self.photo_key(local_path)
        res = self.upload_file(local_path, key, content_type="image/jpeg", public=True)
        if res.get("ok"):
            return {"ok": True, "url": res.get("url", ""), "key": key}
        return res

    def push_products(self, products: list) -> dict:
        body = json.dumps(products, ensure_ascii=False).encode("utf-8")
        res = self.upload_bytes(body, self.catalog_key(), content_type="application/json", public=True)
        if not res.get("ok"):
            return res
        return {"ok": True, "count": len(products), "key": res.get("key", "")}

    def pull_products(self) -> dict:
        try:
            obj = self._client().get_object(Bucket=self.bucket, Key=self.catalog_key())
            raw = obj["Body"].read().decode("utf-8")
            return {"ok": True, "products": json.loads(raw or "[]")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}


class MySQLClient:
    """Внешний каталог товаров в MySQL / MariaDB.

    Нужен только для таблицы каталога. Фото при таком режиме всё равно стоит хранить в S3.
    """

    def __init__(self, host: str, port: int, user: str, password: str,
                 database: str, table: str = "products"):
        self.host = (host or "").strip()
        self.port = int(port or 3306)
        self.user = (user or "").strip()
        self.password = password or ""
        self.database = (database or "").strip()
        self.table = (table or "products").strip() or "products"

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.user and self.database)

    def _conn(self):
        try:
            import pymysql
        except ImportError:
            raise ValueError("Не установлен pymysql: pip install pymysql")
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def _ensure_table(self):
        table = self.table.replace("`", "")
        sql = f"""
        CREATE TABLE IF NOT EXISTS `{table}` (
          id BIGINT PRIMARY KEY,
          code VARCHAR(255) DEFAULT '',
          name VARCHAR(500) NOT NULL,
          category VARCHAR(255) DEFAULT '',
          price INT DEFAULT 0,
          old_price INT DEFAULT 0,
          stock INT DEFAULT -1,
          description LONGTEXT,
          photo TEXT,
          photos JSON,
          storage_location VARCHAR(255) DEFAULT '',
          owner_name VARCHAR(255) DEFAULT '',
          barcode VARCHAR(255) DEFAULT '',
          on_showcase TINYINT(1) DEFAULT 1,
          in_stock TINYINT(1) DEFAULT 1,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)

    def ping(self) -> dict:
        if not self.enabled:
            return {"ok": False, "error": "Не заданы host/user/database"}
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS ok")
                    cur.fetchone()
            return {"ok": True, "status": 200}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def push_products(self, products: list) -> dict:
        try:
            self._ensure_table()
            table = self.table.replace("`", "")
            sql = f"""
            REPLACE INTO `{table}`
            (id, code, name, category, price, old_price, stock, description, photo, photos,
             storage_location, owner_name, barcode, on_showcase, in_stock)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            with self._conn() as conn:
                with conn.cursor() as cur:
                    for p in products:
                        cur.execute(sql, (
                            int(p.get("id") or 0),
                            p.get("code", ""),
                            p.get("name", ""),
                            p.get("category", ""),
                            int(p.get("price") or 0),
                            int(p.get("old_price") or 0),
                            int(p.get("stock") or -1),
                            p.get("description", ""),
                            p.get("photo", ""),
                            json.dumps(p.get("photos") or [], ensure_ascii=False),
                            p.get("storage_location", ""),
                            p.get("owner_name", ""),
                            p.get("barcode", ""),
                            1 if p.get("on_showcase", True) else 0,
                            1 if p.get("in_stock", True) else 0,
                        ))
            return {"ok": True, "count": len(products)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def pull_products(self) -> dict:
        try:
            self._ensure_table()
            table = self.table.replace("`", "")
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT * FROM `{table}` ORDER BY id")
                    rows = cur.fetchall()
            out = []
            for row in rows:
                try:
                    row["photos"] = json.loads(row.get("photos") or "[]")
                except Exception:
                    row["photos"] = []
                row["on_showcase"] = bool(row.get("on_showcase", 1))
                row["in_stock"] = bool(row.get("in_stock", 1))
                out.append(row)
            return {"ok": True, "products": out}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}


def _client(store) -> SupabaseClient:
    c = store.settings.get("cloud") or {}
    return SupabaseClient(c.get("url", ""), c.get("key", ""), c.get("bucket", "shop-photos"))


def local_photo_path(photo: str) -> str:
    if photo and str(photo).startswith("/webapp/"):
        return os.path.join(config.WEBAPP_DIR, str(photo).split("/webapp/", 1)[1])
    return ""


def _product_record(p: dict) -> dict:
    return {
        "id": p["id"],
        "code": p.get("code", ""),
        "name": p["name"],
        "category": p.get("category", ""),
        "price": p.get("price", 0),
        "old_price": p.get("old_price", 0),
        "stock": p.get("stock", -1),
        "description": p.get("description", ""),
        "photo": p.get("photo", ""),
        "photos": p.get("photos", []),
        "storage_location": p.get("storage_location", ""),
        "owner_name": p.get("owner_name", ""),
        "barcode": p.get("barcode", ""),
        "on_showcase": p.get("on_showcase", True),
        "in_stock": p.get("in_stock", True),
    }


def _clients(store) -> tuple:
    c = store.settings.get("cloud") or {}
    provider = c.get("provider") or "s3"
    if provider == "s3":
        c2 = apply_s3_preset(c)
        return provider, S3Client(
            c2.get("s3_endpoint", ""),
            c2.get("s3_access_key", ""),
            c2.get("s3_secret_key", ""),
            c2.get("bucket", "shop-photos"),
            c2.get("s3_region", "ru-central1"),
            photo_prefix=c2.get("photo_prefix", "products"),
            catalog_prefix=c2.get("catalog_prefix", "catalog"),
        )
    if provider == "mysql":
        return provider, MySQLClient(
            c.get("mysql_host", ""),
            c.get("mysql_port", 3306),
            c.get("mysql_user", ""),
            c.get("mysql_password", ""),
            c.get("mysql_database", ""),
            c.get("mysql_table", "products"),
        )
    return provider, SupabaseClient(c.get("url", ""), c.get("key", ""), c.get("bucket", "shop-photos"))


def _photo_client(store, provider, main_client):
    if provider == "mysql":
        c = apply_s3_preset(store.settings.get("cloud") or {})
        s3 = S3Client(
            c.get("s3_endpoint", ""),
            c.get("s3_access_key", ""),
            c.get("s3_secret_key", ""),
            c.get("bucket", "shop-photos"),
            c.get("s3_region", "ru-central1"),
            photo_prefix=c.get("photo_prefix", "products"),
            catalog_prefix=c.get("catalog_prefix", "catalog"),
        )
        return s3 if s3.enabled else None
    return main_client if hasattr(main_client, "upload_photo") else None


def sync_to_cloud(store) -> dict:
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
                continue
            if photo_client is None:
                continue
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
        state = dict(store.settings.get("cloud_state") or {})
        state.update({
            "provider": provider,
            "photos": photo_map,
            "last_sync": datetime.now(timezone.utc).isoformat(),
            "catalog_count": len(prods),
        })
        store.set_cloud_state(state)
    return {
        "ok": products_res.get("ok", False),
        "products": products_res.get("count", 0) if products_res.get("ok") else 0,
        "photos": photos,
        "error": products_res.get("error") or "",
    }


def test_cloud(store) -> dict:
    provider, client = _clients(store)
    return {**client.ping(), "provider": provider}


def resolve_photo_url(store, photo: str) -> str:
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
        st = dict(store.settings.get("cloud_state") or {})
        st.update({
            "provider": provider,
            "photos": photos_map,
            "last_sync": datetime.now(timezone.utc).isoformat(),
        })
        store.set_cloud_state(st)
    return {"ok": pres.get("ok"), "photos": len(photos_map), "error": pres.get("error") or ""}


def restore_from_cloud(store) -> dict:
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
        data = {k: rec.get(k) for k in (
            "code", "name", "category", "price", "old_price", "stock", "description",
            "photo", "photos", "storage_location", "owner_name", "barcode",
            "on_showcase", "in_stock",
        )}
        if existing:
            store.update_product(rec_id, data)
            updated += 1
        else:
            store.add_product({**data, "id": None, "name": rec.get("name") or "Товар из облака"})
            created += 1
    return {"ok": True, "created": created, "updated": updated}


def backup_db_to_cloud(store, *, bucket: str | None = None, prefix: str | None = None) -> dict:
    """Создаёт снимок SQLite и загружает его в S3-совместимое хранилище.

    Сценарий для варианта пользователя:
    - живая база продолжает жить на VPS;
    - резервная копия файла `shop.db` уходит в отдельный bucket, например `shop-backups`.
    """
    cloud = apply_s3_preset(store.settings.get("cloud") or {})
    provider = cloud.get("provider") or "s3"
    if provider != "s3":
        return {"ok": False, "error": "Для бэкапа SQLite включите S3-совместимое облако (например Яндекс Object Storage)."}

    backup_bucket = (bucket or cloud.get("backup_bucket") or "shop-backups").strip()
    backup_prefix = str(prefix or cloud.get("backup_prefix") or "sqlite").strip().strip("/")
    client = S3Client(
        cloud.get("s3_endpoint", ""),
        cloud.get("s3_access_key", ""),
        cloud.get("s3_secret_key", ""),
        backup_bucket,
        cloud.get("s3_region", "ru-central1"),
        photo_prefix=backup_prefix,
        catalog_prefix="catalog",
    )
    if not client.enabled:
        return {"ok": False, "error": "Не заданы endpoint/ключи S3 для резервных копий"}

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix="shop-backup-", suffix=f"-{ts}.db", dir=config.DATA_DIR)
        os.close(fd)
        store.export_sqlite_backup(tmp_path)
        key = _join_key(backup_prefix, f"shop-{ts}.db")
        res = client.upload_file(tmp_path, key, content_type="application/x-sqlite3", public=False)
        if not res.get("ok"):
            return res
        backup_info = {
            "bucket": backup_bucket,
            "key": key,
            "path": f"s3://{backup_bucket}/{key}",
            "size": os.path.getsize(tmp_path),
            "at": datetime.now(timezone.utc).isoformat(),
            "endpoint": cloud.get("s3_endpoint", ""),
            "region": cloud.get("s3_region", ""),
        }
        state = dict(store.settings.get("cloud_state") or {})
        state["backup"] = backup_info
        store.set_cloud_state(state)
        return {"ok": True, **backup_info}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
