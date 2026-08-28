"""Клиент Яндекс Доставки (для бизнеса): расчёт стоимости, ПВЗ/постаматы, создание заказа.

API: https://b2b.taxi.yandex.net/b2b/cargo/integration
Ключи доступа: delivery.yandex.ru → настройки → Интеграция (API-токен / Client id).
Основные методы:
  POST /v1/offers/calculate      — предварительный расчёт стоимости доставки
  GET  /v1/pickup-points         — список ПВЗ/постаматов
  POST /v2/claims/create         — создание заявки на доставку (черновик)
  POST /v2/claims/confirm        — подтверждение заявки
  GET  /v2/claims/{id}           — статус
Все вызовы декорированы защитным парсингом: при любой ошибке/изменении формата API
магазин продолжает работать (фиксированная цена-фолбэк, ручной режим).
"""
import asyncio
import json
import logging
import re
import uuid

import requests

log = logging.getLogger("shop.yandex")


class YandexDeliveryClient:
    def __init__(self, settings: dict):
        cfg = settings.get("yandex", {}) or {}
        self.token = (cfg.get("token") or "").strip()
        self.warehouse_address = (cfg.get("warehouse_address") or "").strip()
        self.base = (cfg.get("base_url") or "https://b2b.taxi.yandex.net/b2b/cargo/integration").rstrip("/")
        self.test_mode = bool(cfg.get("test_mode", True))

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict:
        return {"Authorization": "Bearer " + self.token, "Accept-Language": "ru",
                "Content-Type": "application/json"}

    def calc_price(self, city: str, point_id: str = "", fallback: int = 450) -> dict:
        """Расчёт стоимости доставки курьером (или до ПВЗ, если выбран point_id)."""
        if not self.enabled:
            return {"price": fallback, "calculated": False, "error": "Яндекс Доставка не настроена"}
        try:
            end = {}
            if point_id:
                end = {"point_id": point_id}
            elif city:
                end = {"address": {"fullname": "Россия, " + city}}
            else:
                end = {"address": {"fullname": "Россия, Москва"}}
            body = {
                "route_points": [
                    {"type": "source", "address": {"fullname": self.warehouse_address or "Россия, Москва"}},
                    {"type": "destination", **end},
                ],
                "client_requirements": {"taxi_class": "courier"},
            }
            r = requests.post(self.base + "/v1/offers/calculate", json=body,
                              headers=self._headers(), timeout=20)
            r.raise_for_status()
            data = r.json()
            options = data.get("options") or data.get("offers") or data.get("delivery_options") or []
            best = None
            for opt in options:
                if not isinstance(opt, dict):
                    continue
                cost = opt.get("cost") or opt.get("price") or {}
                value = cost.get("value") if isinstance(cost, dict) else cost
                try:
                    v = float(value)
                    best = v if best is None else min(best, v)
                except (TypeError, ValueError):
                    continue
            if best is None:
                return {"price": fallback, "calculated": False, "error": "Яндекс не вернул тариф"}
            return {"price": int(round(best)), "calculated": True, "error": None}
        except Exception as e:
            log.warning("Яндекс Доставка calc: %s", e)
            return {"price": fallback, "calculated": False, "error": str(e)}

    def get_points(self, city: str = "") -> list:
        """Список ПВЗ/постаматов Яндекс Доставки."""
        if not self.enabled:
            raise ValueError("Яндекс Доставка не настроена (нет токена)")
        try:
            r = requests.get(self.base + "/v1/pickup-points",
                             headers=self._headers(), params={"locale": "ru"}, timeout=20)
            r.raise_for_status()
            data = r.json()
            raw = None
            if isinstance(data, dict):
                for key in ("points", "pickup_points", "items", "content"):
                    if isinstance(data.get(key), list):
                        raw = data[key]
                        break
            elif isinstance(data, list):
                raw = data
            points = []
            for item in raw or []:
                if not isinstance(item, dict):
                    continue
                address = item.get("address") or {}
                addr_str = ""
                if isinstance(address, dict):
                    addr_str = address.get("fullname") or address.get("comment") or ""
                point = {
                    "id": str(item.get("id") or item.get("point_id") or ""),
                    "name": item.get("name") or item.get("title") or "ПВЗ Яндекс",
                    "address": addr_str or item.get("description", ""),
                    "city": "",
                    "work_time": "",
                }
                if point["id"]:
                    points.append(point)
            if city.strip():
                q = city.strip().lower()
                points = [p for p in points if q in (p.get("address") or "").lower()
                          or q in (p.get("name") or "").lower()]
            return points
        except Exception as e:
            log.warning("Яндекс Доставка points: %s", e)
            raise ValueError(f"Не удалось загрузить ПВЗ Яндекса: {e}")

    def create_order(self, order: dict) -> dict:
        """Создание заявки на доставку после оплаты."""
        if not self.enabled:
            raise ValueError("Яндекс Доставка не настроена")
        c = order.get("customer") or {}
        point_id = str(c.get("point_id") or "").strip()
        if not c.get("address") and not point_id:
            raise ValueError("Нет адреса или ПВЗ для доставки")
        dest = {"type": "destination"}
        if point_id:
            dest["point_id"] = point_id
        else:
            dest["address"] = {"fullname": c.get("address")}
        items = []
        for it in order.get("items", []):
            items.append({"title": it["name"][:200], "quantity": it["qty"],
                          "cost_value": str(float(it["price"])), "cost_currency": "RUB"})
        body = {
            "route_points": [
                {"type": "source", "address": {"fullname": self.warehouse_address or "Россия, Москва"},
                 "skip_confirmation": True},
                dest,
            ],
            "items": items,
            "comment": f"Заказ {order['id']} — {order['customer'].get('comment') or ''}"[:200],
            "emergency_contact": {"name": c.get("name", ""), "phone": re.sub(r"\D", "", c.get("phone", "")) or "+70000000000"},
            "client_requirements": {"taxi_class": "courier"},
            "optional_return": False,
        }
        rid = str(uuid.uuid4())
        r = requests.post(self.base + f"/v2/claims/create?request_id={rid}", json=body,
                          headers=self._headers(), timeout=30)
        r.raise_for_status()
        data = r.json()
        claim_id = data.get("id") or data.get("claim_id")
        if not claim_id:
            raise ValueError("Яндекс не вернул ID заявки: " + str(data)[:200])
        # подтверждение (если заявка не подтверждается автоматически)
        try:
            requests.post(self.base + f"/v2/claims/confirm?claim_id={claim_id}",
                          headers=self._headers(), timeout=20)
        except Exception as e:
            log.warning("Яндекс confirm: %s", e)
        return {"id": str(claim_id), "raw": data}


def extract_tracking(response: dict) -> str:
    data = response or {}
    if isinstance(data, dict) and data.get("id"):
        return str(data["id"])
    return json.dumps(data, ensure_ascii=False)[:120]


async def create_delivery_order(store, order_id: str, notify=None) -> dict:
    """После оплаты передаёт заказ в Яндекс Доставку (если способ доставки — yandex)."""
    order = store.get_order(order_id)
    if not order or order.get("delivery_method") != "yandex":
        return {"skipped": True}
    client = YandexDeliveryClient(store.settings)
    if not client.enabled:
        text = (f"⚠️ Заказ {order_id}: Яндекс Доставка не настроен (нет токена) — "
                "передайте заказ вручную в кабинете delivery.yandex.ru.")
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
        text = f"🚕 Заказ {order_id} передан в Яндекс Доставку. ID заявки: {tracking}"
        log.info(text)
        if notify:
            try:
                await notify(text)
            except Exception:
                pass
        return {"ok": True, "tracking": tracking}
    except Exception as e:
        log.warning("Яндекс Доставка: не удалось передать заказ %s: %s", order_id, e)
        text = (f"⚠️ Не удалось передать заказ {order_id} в Яндекс Доставку: {e}\n"
                "Создайте заявку вручную в кабинете delivery.yandex.ru.")
        if notify:
            try:
                await notify(text)
            except Exception:
                pass
        return {"ok": False, "error": str(e)}
