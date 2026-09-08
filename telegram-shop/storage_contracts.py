"""Stable provider contracts for database and photo storage adapters (block 13).

Все провайдеры каталога (SQLite, Supabase, MySQL/MariaDB, S3-JSON) реализуют
`DatabaseProvider`: смена провайдера не требует изменения бизнес-логики.
`provider_status` возвращает безопасный статус и никогда не сериализует секреты.
"""
from typing import Protocol, runtime_checkable

@runtime_checkable
class DatabaseProvider(Protocol):
    def ping(self) -> dict: ...
    def push_products(self, products: list) -> dict: ...
    def pull_products(self) -> dict: ...
    def catalog(self) -> dict: ...
    def upsert_product(self, product: dict) -> dict: ...
    def upsert_stock(self, items: list) -> dict: ...
    def apply_batch(self, ops: list) -> dict: ...

class DatabaseProviderMixin:
    """Единая реализация контракта поверх push/pull каталога.

    Провайдер может переопределить любой метод более дешёвым нативным
    (например, MySQL делает UPDATE по коду вместо перезаливки каталога).
    Ошибки возвращаются как {"ok": False, "error": "..."} — понятное сообщение
    без 500 и без секретов.
    """

    def catalog(self) -> dict:
        """Полный каталог: {"ok": True, "products": [...]}."""
        return self.pull_products()

    def upsert_product(self, product: dict) -> dict:
        """Создать/обновить один товар."""
        return self.push_products([product])

    def upsert_stock(self, items: list) -> dict:
        """Обновить остатки/цены по кодам: [{"code", "stock", "price"}, ...]."""
        pull = self.pull_products()
        if not pull.get("ok"):
            return {"ok": False, "error": pull.get("error") or "каталог недоступен"}
        by_code = {}
        for p in pull.get("products") or []:
            code = str((p or {}).get("code") or "").strip()
            if code:
                by_code[code] = p
        updated, missing = 0, []
        for it in items or []:
            code = str((it or {}).get("code") or "").strip()
            rec = by_code.get(code)
            if not rec:
                missing.append(code)
                continue
            try:
                if it.get("stock") is not None:
                    rec["stock"] = int(it["stock"])
                if it.get("price") is not None:
                    rec["price"] = int(it["price"])
                if it.get("old_price") is not None:
                    rec["old_price"] = int(it["old_price"])
            except (TypeError, ValueError):
                return {"ok": False, "error": f"нечисловые stock/price у кода {code!r}"}
            updated += 1
        if not updated:
            return {"ok": True, "updated": 0, "missing": missing}
        push = self.push_products(list(by_code.values()))
        if not push.get("ok"):
            return {"ok": False, "error": push.get("error") or "ошибка записи каталога"}
        return {"ok": True, "updated": updated, "missing": missing}

    def apply_batch(self, ops: list) -> dict:
        """Батч операций (товары и остатки).

        Для провайдеров без серверных транзакций применяется best-effort:
        каждая операция выполняется целиком, результат содержит счётчики.
        """
        applied, failed, errors = 0, 0, []
        for op in ops or []:
            kind = (op or {}).get("type")
            if kind == "product":
                res = self.upsert_product(op.get("record") or {})
            elif kind == "stock":
                res = self.upsert_stock(op.get("items") or [])
            else:
                res = {"ok": False, "error": f"неизвестный тип операции: {kind!r}"}
            if res.get("ok"):
                applied += 1
            else:
                failed += 1
                errors.append(str(res.get("error") or ""))
        return {"ok": failed == 0, "applied": applied, "failed": failed, "errors": errors[:5]}

@runtime_checkable
class PhotoStorage(Protocol):
    @property
    def enabled(self) -> bool: ...
    def ping(self) -> dict: ...
    def upload_photo(self, local_path: str) -> dict: ...
    def delete_photo(self, photo_ref: str) -> dict: ...
    def public_url(self, photo_ref: str) -> str: ...

def provider_status(provider) -> dict:
    """Common safe status response; never serializes credentials."""
    try:
        result = provider.ping()
        return {"ok": bool(result.get("ok")), "status": result.get("status", 200 if result.get("ok") else 503), "error": result.get("error", "")}
    except Exception as exc:
        return {"ok": False, "status": 503, "error": str(exc)[:200]}


@runtime_checkable
class BackupStorage(Protocol):
    def upload_backup(self, local_path: str, key: str) -> dict: ...
    def download_backup(self, key: str, local_path: str) -> dict: ...
    def verify_checksum(self, key: str, sha256: str) -> bool: ...
