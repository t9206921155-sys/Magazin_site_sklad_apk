"""Диспетчер передачи оплаченных заказов в службы доставки."""
import logging

import fivepost
import yandex_delivery

log = logging.getLogger("shop.delivery")


async def after_payment(store, order_id: str, notify_admin=None) -> dict:
    """После успешной оплаты передаёт заказ в соответствующую службу доставки."""
    order = store.get_order(order_id)
    if not order:
        return {"skipped": True}
    method = order.get("delivery_method")
    if method == "fivepost":
        return await fivepost.create_delivery_order(store, order_id, notify_admin)
    if method == "yandex":
        return await yandex_delivery.create_delivery_order(store, order_id, notify_admin)
    if method == "cdek":
        # СДЭК: заказ оформляется вручную или через отдельную интеграцию — напоминаем админу
        if notify_admin:
            try:
                await notify_admin(f"📦 Заказ {order_id} оплачен (доставка СДЭК). Оформите отправление в ЛК СДЭК.")
            except Exception:
                pass
        return {"skipped": True, "reason": "manual"}
    return {"skipped": True}
