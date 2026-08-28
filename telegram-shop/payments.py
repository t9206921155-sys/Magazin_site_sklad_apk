"""Платёжные провайдеры: test (имитация), ЮKassa (карты/СБП), CryptoBot (TON/USDT), Telegram Stars.

Все провайдеры работают по схеме: создать платёж -> заказ ждёт подтверждения ->
подтверждение приходит либо сразу (test), либо через вебхук (yookassa/cryptobot),
либо через событие successful_payment в боте (stars).
"""
import asyncio
import hashlib
import logging
import uuid

import requests
from aiogram.types import LabeledPrice

import config

log = logging.getLogger("shop.payments")


class TestPaymentProvider:
    """Имитация оплаты — деньги не списываются."""
    name = "test"

    async def pay_order(self, store, order_id: str) -> dict:
        order = store.get_order(order_id)
        if order is None:
            raise ValueError("Заказ не найден")
        return store.confirm_payment(order_id, "test", "TEST-" + uuid.uuid4().hex[:8].upper())


class YooKassaProvider:
    """ЮKassa: банковские карты РФ, СБП, кошельки. REST API v3.
    https://yookassa.ru/developers — регистрация магазина, shopId + секретный ключ.
    """
    name = "yookassa"
    API = "https://api.yookassa.ru/v3"

    def _payments(self, store) -> dict:
        return store.settings["payments"]["yookassa"]

    async def pay_order(self, store, order_id: str) -> dict:
        order = store.get_order(order_id)
        if not order:
            raise ValueError("Заказ не найден")
        cfg = self._payments(store)
        base = config.WEBAPP_URL or f"http://localhost:{config.PORT}"
        body = {
            "amount": {"value": f"{order['total']}.00", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": f"{base}/#/success/{order_id}"},
            "description": f"Заказ {order_id} в {store.settings['shop_name']}",
            "metadata": {"order_id": order_id},
        }
        try:
            resp = await asyncio.to_thread(
                requests.post, f"{self.API}/payments", json=body,
                auth=(cfg["shop_id"], cfg["secret_key"]), timeout=15)
            data = resp.json()
        except Exception as e:
            log.warning("ЮKassa: ошибка создания платежа: %s", e)
            raise ValueError("Не удалось создать платёж ЮKassa. Проверьте настройки.")
        if resp.status_code >= 400:
            log.warning("ЮKassa: %s %s", resp.status_code, data)
            raise ValueError("Ошибка ЮKassa: " + str(data.get("description", resp.status_code)))
        payment_id = data["id"]
        store.mark_payment_pending(order_id, "yookassa", payment_id)
        return {"provider": "yookassa", "payment_id": payment_id,
                "confirmation_url": data["confirmation"]["confirmation_url"]}


class CryptoBotProvider:
    """CryptoBot (Crypto Pay): оплата TON, USDT и др. https://t.me/CryptoBot -> Crypto Pay -> токен."""
    name = "cryptobot"
    API = "https://pay.crypt.bot/api"

    def _cfg(self, store) -> dict:
        return store.settings["payments"]["cryptobot"]

    async def pay_order(self, store, order_id: str) -> dict:
        order = store.get_order(order_id)
        if not order:
            raise ValueError("Заказ не найден")
        cfg = self._cfg(store)
        body = {
            "asset": cfg["asset"],
            "amount": str(order["total"]),
            "description": f"Заказ {order_id}",
            "payload": order_id,
            "allow_anonymous": True,
        }
        try:
            resp = await asyncio.to_thread(
                requests.post, f"{self.API}/createInvoice", json=body,
                headers={"Crypto-Pay-API-Token": cfg["api_token"]}, timeout=15)
            data = resp.json()
        except Exception as e:
            log.warning("CryptoBot: ошибка: %s", e)
            raise ValueError("Не удалось создать счёт CryptoBot. Проверьте токен.")
        if not data.get("ok"):
            log.warning("CryptoBot: %s", data)
            raise ValueError("Ошибка CryptoBot: " + str(data.get("error", {}).get("name", "?")))
        inv = data["result"]
        store.mark_payment_pending(order_id, "cryptobot", str(inv["invoice_id"]))
        return {"provider": "cryptobot", "payment_id": inv["invoice_id"], "pay_url": inv["pay_url"]}


class StarsProvider:
    """Telegram Stars: счёт выставляет бот прямо в чате (XTR). Без внешних регистраций."""
    name = "stars"

    def __init__(self, bot=None):
        self.bot = bot

    async def pay_order(self, store, order_id: str) -> dict:
        if not self.bot:
            raise ValueError("Бот не запущен (нет BOT_TOKEN)")
        order = store.get_order(order_id)
        if not order:
            raise ValueError("Заказ не найден")
        if not order.get("tg_user_id"):
            raise ValueError("Оплата звёздами доступна только внутри Telegram")
        rate = float(store.settings["payments"]["stars"].get("rate", 1.0))
        amount = max(1, int(round(order["total"] * rate)))
        await self.bot.send_invoice(
            order["tg_user_id"],
            title=f"Заказ {order_id}",
            description=f"Оплата заказа в {store.settings['shop_name']}",
            payload=order_id,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"Заказ {order_id}", amount=amount)],
        )
        store.mark_payment_pending(order_id, "stars", None)
        return {"provider": "stars", "stars_amount": amount,
                "message": "Счёт выставлен в чате с ботом — откройте чат и оплатите звёздами."}


class TbankProvider:
    """Т-Банк (Тинькофф) интернет-эквайринг: карты, СБП. API v2.

    https://developer.tbank.ru/eacq/api/init
    Реквизиты: личный кабинет Т-Бизнеса → Эквайринг → терминал
    (TerminalKey + пароль). Тестовый терминал выдаётся там же (ключ с суффиксом DEMO).
    Подпись Token: SHA-256 от склейки всех параметров (кроме Token, DATA, Receipt),
    отсортированных по алфавиту, + пароль терминала.
    """
    name = "tbank"
    API = "https://securepay.tinkoff.ru/v2"

    EXCLUDE_FROM_TOKEN = ("Token", "DATA", "Receipt")

    @staticmethod
    def sign(params: dict, password: str) -> str:
        items = sorted(
            (str(k), v) for k, v in params.items()
            if k not in TbankProvider.EXCLUDE_FROM_TOKEN and v is not None and v != ""
        )
        return hashlib.sha256("".join(k + str(v) for k, v in items).encode() + password.encode()).hexdigest()

    def _cfg(self, store) -> dict:
        return store.settings["payments"]["tbank"]

    async def pay_order(self, store, order_id: str) -> dict:
        order = store.get_order(order_id)
        if not order:
            raise ValueError("Заказ не найден")
        cfg = self._cfg(store)
        if not cfg.get("terminal_key") or not cfg.get("password"):
            raise ValueError("Не заданы реквизиты Т-Банка (админка → Настройки → Оплата)")
        base = config.WEBAPP_URL or f"http://localhost:{config.PORT}"
        params = {
            "TerminalKey": cfg["terminal_key"],
            "Amount": int(order["total"]) * 100,      # в копейках
            "OrderId": order_id,
            "Description": f"Заказ {order_id} в {store.settings['shop_name']}",
            "SuccessURL": f"{base}/#/success/{order_id}",
            "FailURL": f"{base}/#/pay/{order_id}",
            "NotificationURL": f"{base}/webhook/tbank",
        }
        params["Token"] = self.sign(params, cfg["password"])
        try:
            resp = await asyncio.to_thread(requests.post, self.API + "/Init", json=params, timeout=20)
            data = resp.json()
        except Exception as e:
            log.warning("Т-Банк: ошибка Init: %s", e)
            raise ValueError("Не удалось создать платёж Т-Банка. Проверьте реквизиты и доступность API.")
        if not data.get("Success"):
            raise ValueError("Т-Банк: " + str(data.get("Details") or data.get("Message") or data.get("ErrorCode")))
        payment_id = str(data["PaymentId"])
        store.mark_payment_pending(order_id, "tbank", payment_id)
        return {"provider": "tbank", "payment_id": payment_id,
                "confirmation_url": data["PaymentURL"]}


class TransferProvider:
    """Перевод по СБП/карте: подходит для продавцов-физлиц.
    Покупатель видит реквизиты (телефон/карта), переводит деньги и нажимает «Я оплатил».
    Админ проверяет поступление и подтверждает заказ вручную (админка или бот)."""
    name = "transfer"

    async def pay_order(self, store, order_id: str) -> dict:
        order = store.get_order(order_id)
        if not order:
            raise ValueError("Заказ не найден")
        store.mark_transfer_reported(order_id)
        return {"provider": "transfer", "status": "verifying",
                "message": "Спасибо! Мы проверим поступление и подтвердим заказ. "
                           "Статус обновится автоматически после проверки."}


def get_payment_providers(bot=None):
    return {
        "test": TestPaymentProvider(),
        "transfer": TransferProvider(),
        "yookassa": YooKassaProvider(),
        "cryptobot": CryptoBotProvider(),
        "stars": StarsProvider(bot),
        "tbank": TbankProvider(),
    }
