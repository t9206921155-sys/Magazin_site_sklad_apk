"""Клиент 5POST (fivepost.ru) — доставка в постаматы и ПВЗ X5 (Пятёрочка, Перекрёсток).

Договор: fivepost.ru/become-partner → персональный менеджер выдаёт api-key и warehouse_id.
Схема авторизации: api-key -> JWT (живёт 1 час) -> заголовок Authorization: Bearer.
Среды: prod  https://api-omni.x5.ru | test  https://api-preprod-omni.x5.ru

Методы (v1):
  POST /jwt-generate-claims/rs256/1?apikey=...   (form: subject=OpenAPI, audience=A122019!)
  POST /api/v1/pickuppoints/query                {pageSize, pageNumber} — список постаматов/ПВЗ
  POST /api/v1/createOrder                       {partnerOrders: [...]} — создание заказа
  DELETE /api/v1/cancelOrder/{id}                — отмена
  POST /api/v1/getOrderStatus                    [{senderOrderId}] — статусы
"""
import asyncio
import json
import logging
import re
import time

import requests

log = logging.getLogger("shop.fivepost")

TEST_API = "https://api-preprod-omni.x5.ru"
PROD_API = "https://api-omni.x5.ru"

_jwt_cache = {"jwt": None, "ts": 0, "key": None}

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "7" + digits
    return "+" + digits if digits else ""


class FivePostClient:
    def __init__(self, settings: dict, shop_name: str = ""):
        cfg = settings.get("fivepost", {}) or {}
        self.api_key = (cfg.get("api_key") or "").strip()
        self.warehouse_id = (cfg.get("warehouse_id") or "").strip()
        self.brand_name = (cfg.get("brand_name") or "").strip() or shop_name
        self.test_mode = bool(cfg.get("test_mode", True))
        self.base = TEST_API if self.test_mode else PROD_API

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------ auth
    def _jwt(self) -> str:
        if not self.api_key:
            raise ValueError("Не задан api-key 5POST (админка → Настройки → Доставка)")
        key = self.api_key + self.base
        if _jwt_cache["jwt"] and _jwt_cache["key"] == key and time.time() - _jwt_cache["ts"] < 3000:
            return _jwt_cache["jwt"]
        r = requests.post(
            f"{self.base}/jwt-generate-claims/rs256/1?apikey={self.api_key}",
            data={"subject": "OpenAPI", "audience": "A122019!"}, timeout=20)
        r.raise_for_status()
        data = r.json()
        if not data.get("jwt"):
            raise ValueError("5POST не выдал JWT: " + str(data))
        _jwt_cache.update(jwt=data["jwt"], ts=time.time(), key=key)
        return data["jwt"]

    def _post(self, path: str, payload: dict, timeout: int = 30) -> dict:
        r = requests.post(self.base + path, json=payload,
                          headers={"Authorization": "Bearer " + self._jwt()}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            if data.get("error"):
                raise ValueError("5POST: " + str(data.get("message") or data.get("error")))
            if data.get("status") not in (None, "OK", "ok"):
                raise ValueError("5POST: " + str(data.get("description") or data.get("message") or data))
        return data

    # ------------------------------------------------------------------ методы
    def get_pickup_points(self, page: int = 0, size: int = 500) -> list:
        data = self._post("/api/v1/pickuppoints/query", {"pageSize": size, "pageNumber": page})
        # ответ может быть {content:[...]} / {data:[...]} / просто списком
        raw = None
        if isinstance(data, dict):
            for key in ("content", "data", "items", "pickupPoints", "points"):
                if isinstance(data.get(key), list):
                    raw = data[key]
                    break
        elif isinstance(data, list):
            raw = data
        points = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            points.append({
                "id": item.get("id") or item.get("uuid") or "",
                "mdm_code": item.get("mdmCode") or item.get("mdm_code") or "",
                "name": item.get("name") or item.get("title") or "5POST",
                "address": item.get("address") or "",
                "city": item.get("city") or "",
                "work_time": item.get("workTime") or item.get("work_time") or "",
            })
        return points

    def create_order(self, order: dict) -> dict:
        """Передаёт оплаченный заказ магазина в 5POST. Возвращает ответ API."""
        if not self.warehouse_id:
            raise ValueError("Не задан склад забора (warehouse_id) 5POST")
        c = order.get("customer") or {}
        point = str(c.get("point_id") or "").strip()
        if not point:
            raise ValueError("Не выбран постамат 5POST")
        location = ({"receiverLocation": point} if UUID_RE.match(point)
                    else {"receiverLocationMDM": point})

        cargo = {
            "senderCargoId": order["id"],
            "barcodes": [{"value": order["id"]}],
            "currency": "RUB",
            "price": float(order.get("subtotal", 0)),
            "height": 150, "length": 200, "width": 100,
            "weight": 500000,  # мг (500 г по умолчанию)
            "vat": None,
        }
        partner_order = {
            "senderOrderId": order["id"],
            "brandName": self.brand_name or "Интернет-магазин",
            "clientOrderId": order["id"],
            "clientName": str(c.get("name") or ""),
            "clientPhone": normalize_phone(c.get("phone")),
            **location,
            "senderLocation": self.warehouse_id,
            "returnLocation": self.warehouse_id,
            "undeliverableOption": "RETURN",
            "cost": {
                "paymentValue": 0.0,              # предоплата — получатель ничего не платит
                "paymentCurrency": "RUB",
                "paymentType": "PREPAYMENT",
                "price": float(order.get("subtotal", 0)),
                "priceCurrency": "RUB",
                "deliveryCost": float(order.get("delivery_price", 0)),
            },
            "cargoes": [cargo],
        }
        if c.get("email"):
            partner_order["clientEmail"] = c["email"]
        data = self._post("/api/v1/createOrder", {"partnerOrders": [partner_order]}, timeout=60)
        return data

    def cancel_order(self, fivepost_order_id: str) -> dict:
        r = requests.delete(f"{self.base}/api/v1/cancelOrder/{fivepost_order_id}",
                            headers={"Authorization": "Bearer " + self._jwt()}, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_order_status(self, sender_order_id: str) -> dict:
        return self._post("/api/v1/getOrderStatus", [{"senderOrderId": sender_order_id}])


def extract_tracking(response: dict) -> str:
    """Вытаскивает идентификатор заказа 5POST из ответа createOrder (защитно)."""
    data = response or {}
    if isinstance(data, dict) and isinstance(data.get("orders"), list) and data["orders"]:
        data = data["orders"][0]
    if not isinstance(data, dict):
        return str(data)[:64] or "—"
    for key in ("orderId", "vendorOrderId", "id", "uuid", "senderOrderId"):
        v = data.get(key)
        if v:
            return str(v)
    return json.dumps(data, ensure_ascii=False)[:120]


async def create_delivery_order(store, order_id: str, notify=None) -> dict:
    """После оплаты передаёт заказ в 5POST (если способ доставки — fivepost).

    notify — async-функция уведомления админов (или None).
    """
    order = store.get_order(order_id)
    if not order or order.get("delivery_method") != "fivepost":
        return {"skipped": True}
    client = FivePostClient(store.settings, store.settings["shop_name"])
    if not client.enabled:
        text = (f"⚠️ Заказ {order_id}: 5POST не настроен (нет api-key) — "
                "передайте заказ вручную в личном кабинете 5POST.")
        log.warning(text)
        if notify:
            try:
                await notify(text)
            except Exception:
                pass
        return {"skipped": True, "reason": "not_configured"}
    try:
        response = await asyncio.to_thread(client.create_order, order)
        tracking = extract_tracking(response)
        store.set_delivery_tracking(order_id, tracking, response)
        text = f"📦 Заказ {order_id} передан в 5POST. Номер в 5POST: {tracking}"
        log.info(text)
        if notify:
            try:
                await notify(text)
            except Exception:
                pass
        return {"ok": True, "tracking": tracking}
    except Exception as e:
        log.warning("5POST: не удалось передать заказ %s: %s", order_id, e)
        text = (f"⚠️ Не удалось передать заказ {order_id} в 5POST: {e}\n"
                "Создайте заказ вручную в личном кабинете 5POST.")
        if notify:
            try:
                await notify(text)
            except Exception:
                pass
        return {"ok": False, "error": str(e)}
