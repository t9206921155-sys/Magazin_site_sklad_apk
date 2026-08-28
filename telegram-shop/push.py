"""Web Push (VAPID) для PWA «Склад» и Mini App.

Работает только на HTTPS (требование браузеров для Push API).
На http-превью подписка невозможна — интерфейс это учитывает и молча отключает push.

Ключи VAPID генерируются автоматически при первом использовании и хранятся в настройках
(warehouse.vapid_public / warehouse.vapid_private; приватный защищён от затирания).
"""
import json
import logging

log = logging.getLogger("shop.push")

try:
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid01
    HAS_WEBPUSH = True
except Exception:  # библиотека не установлена — push отключён
    HAS_WEBPUSH = False


def _vapid(store):
    if not HAS_WEBPUSH:
        return None, None
    w = store.settings.get("warehouse") or {}
    if w.get("vapid_public") and w.get("vapid_private"):
        return w["vapid_public"], w["vapid_private"]
    v = Vapid01()
    v.generate_keys()
    priv = v.private_pem().decode()
    pub = v.public_pem().decode()
    store.update_settings({"warehouse": {**w, "vapid_public": pub, "vapid_private": priv}})
    return pub, priv


def vapid_public(store) -> str:
    pub, _ = _vapid(store)
    return pub or ""


def send_push(store, user_ids, title: str, body: str, url: str = "/warehouse/") -> int:
    """Отправляет push всем подпискам указанных пользователей склада (0 = все)."""
    if not HAS_WEBPUSH:
        return 0
    pub, priv = _vapid(store)
    if not pub or not priv:
        return 0
    subs = store.wh_push_subs(0)
    if user_ids:
        ids = {int(u) for u in user_ids}
        subs = [s for s in subs if int(s.get("user_id") or 0) in ids]
    sent = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.get("endpoint"),
                    "keys": {"p256dh": sub.get("keys", {}).get("p256dh"),
                             "auth": sub.get("keys", {}).get("auth")},
                },
                data=json.dumps({"title": title, "body": body}, ensure_ascii=False),
                vapid_private_key=priv,
                vapid_claims={"sub": "mailto:admin@telegramshop.local"},
                headers={"TTL": "86400"},
            )
            sent += 1
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):
                # подписка больше не действительна — удаляем
                try:
                    store.wh_push_remove(int(sub.get("user_id") or 0), str(sub.get("endpoint") or ""))
                except Exception:
                    pass
            else:
                log.warning("push не доставлен: %s", e)
        except Exception as e:
            log.warning("push ошибка: %s", e)
    return sent
