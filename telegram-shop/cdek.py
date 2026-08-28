"""Клиент СДЭК: расчёт стоимости доставки по API v2.0.
Реквизиты (client_id / client_secret) выдаются в личном кабинете СДЭК
(lk.cdek.ru → Интеграция → Создать новый ключ) после заключения договора.
Впишите их в админке: Настройки → Доставка → СДЭК.
Публичные тестовые реквизиты СДЭК периодически меняет — используйте свои.
"""
import logging
import time

import requests

log = logging.getLogger("shop.cdek")

TEST_API = "https://api.edu.cdek.ru/v2"
PROD_API = "https://api.cdek.ru/v2"

_token_cache = {"token": None, "ts": 0, "key": None}


def _client(settings: dict):
    cfg = settings.get("cdek", {})
    account = (cfg.get("account") or "").strip()
    password = (cfg.get("password") or "").strip()
    api = TEST_API if cfg.get("use_test_env", True) and not account else PROD_API
    return account, password, api


def _token(settings: dict) -> str:
    account, password, api = _client(settings)
    if not account or not password:
        raise ValueError("Не заданы реквизиты СДЭК (админка → Настройки → Доставка)")
    key = account + api
    if _token_cache["token"] and _token_cache["key"] == key and time.time() - _token_cache["ts"] < 3000:
        return _token_cache["token"]
    r = requests.post(
        f"{api}/oauth/token?grant_type=client_credentials&client_id={account}&client_secret={password}",
        timeout=12)
    r.raise_for_status()
    token = r.json()["access_token"]
    _token_cache.update(token=token, ts=time.time(), key=key)
    return token


def find_city(settings: dict, name: str) -> int:
    """Код города СДЭК по названию (например, «Москва» -> 44)."""
    account, password, api = _client(settings)
    r = requests.get(f"{api}/location/cities", params={"city": name, "country_codes": "RU"},
                     headers={"Authorization": "Bearer " + _token(settings)}, timeout=12)
    r.raise_for_status()
    for c in r.json():
        return int(c["code"])
    raise ValueError(f"Город «{name}» не найден в СДЭК")


def calc(settings: dict, to_city: str, weight_g: int = 1000, tariff: int = 137) -> int:
    """Стоимость доставки в рублях (тариф 137 = посылка склад-склад)."""
    account, password, api = _client(settings)
    to_code = find_city(settings, to_city)
    body = {
        "type": 1,
        "currency": 1,
        "lang": "rus",
        "from_location": {"code": int(settings.get("cdek", {}).get("from_city", 44))},
        "to_location": {"code": to_code},
        "packages": [{"weight": max(100, weight_g), "length": 10, "width": 10, "height": 10}],
    }
    if tariff:
        body["tariff_code"] = int(tariff)
    r = requests.post(f"{api}/calculator/tarifflist", json=body,
                      headers={"Authorization": "Bearer " + _token(settings)}, timeout=12)
    r.raise_for_status()
    data = r.json()
    if data.get("tariff_codes"):
        return int(float(data["tariff_codes"][0]["total_sum"]))
    raise ValueError("СДЭК не вернул тарифы")


def calc_or_fallback(settings: dict, to_city: str, fallback: int, weight_g: int = 1000) -> dict:
    """Расчёт с мягким фолбэком: при любой ошибке API возвращаем фиксированную цену."""
    try:
        price = calc(settings, to_city, weight_g)
        return {"price": price, "calculated": True, "error": None}
    except Exception as e:
        log.warning("СДЭК: %s", e)
        return {"price": fallback, "calculated": False, "error": str(e)}
