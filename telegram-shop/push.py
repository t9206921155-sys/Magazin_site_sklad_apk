"""Web Push (VAPID) для PWA «Склад» и Mini App.

Работает только на HTTPS (требование браузеров для Push API).
На http-превью подписка невозможна — интерфейс это учитывает и молча отключает push.

Ключи VAPID генерируются автоматически при первом использовании и хранятся в настройках
(warehouse.vapid_public / warehouse.vapid_private; приватный защищён от затирания).
"""
import json
import logging

import config

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


# ------------------------------------------------------------------ FCM (блок 29, ТЗ §6.2)
# Граница провайдера (та же конвенция, что у остальных): без credentials или
# при FCM_DRY_RUN=1 реальных отправок нет — только диагностика. Боевой
# транспорт (FCM HTTP v1 + OAuth2 service account) включается на staging
# в Фазе 5 после проверки google-services.json/FCM-проекта владельца.

def fcm_configured() -> bool:
    return bool(config.FCM_CREDENTIALS_JSON)


def fcm_status(store) -> dict:
    dry = config.FCM_DRY_RUN or not fcm_configured()
    return {"configured": fcm_configured(), "dry_run": dry,
            "devices": store.mobile_devices_count(),
            "transport": "pending-staging" if dry else "fcm-http-v1"}


def send_fcm(store, guest_ids, title: str, body: str, data: dict = None) -> dict:
    """Push покупателям. Никогда не бросает исключения наружу (хуки безопасны).

    Возвращает {"sent": N, "dry_run": bool, "skipped_no_device": M}.
    Токены в логи не пишутся (только маски guest_id).
    """
    data = data or {}
    try:
        targets = store.mobile_devices_for(guest_ids)
    except Exception as e:
        log.warning("fcm: не удалось прочитать устройства: %s", e)
        return {"sent": 0, "dry_run": True, "skipped_no_device": 0}
    wanted = {str(g) for g in (guest_ids or []) if str(g).strip()}
    skipped = len(wanted - {t["guest_id"] for t in targets})
    if not targets:
        return {"sent": 0, "dry_run": True, "skipped_no_device": skipped}
    if config.FCM_DRY_RUN or not fcm_configured():
        log.info("fcm dry-run: '%s' → %d устр. (guest: %s)",
                 title, len(targets),
                 ",".join(t["guest_id"][:4] + "…" for t in targets[:5]))
        return {"sent": 0, "dry_run": True, "skipped_no_device": skipped}
    # Боевой транспорт — staging (Фаза 5): без OAuth2 service account
    # отправлять нечем, поэтому честно остаёмся в dry-run.
    log.warning("fcm: credentials заданы, но транспорт pending-staging — отправка пропущена")
    return {"sent": 0, "dry_run": True, "skipped_no_device": skipped,
            "note": "transport-pending-staging"}


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
