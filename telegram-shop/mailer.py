"""Email-уведомления продавцам маркетплейса (SMTP).
Настройки — админка → Настройки → Маркетплейс (SMTP-блок).
Без настроенного SMTP письма молча пропускаются (логируется reason).
"""
import asyncio
import logging
import smtplib
from email.header import Header
from email.mime.text import MIMEText

log = logging.getLogger("shop.mailer")


def _cfg(store) -> dict:
    return store.settings.get("smtp") or {}


def available(store) -> bool:
    c = _cfg(store)
    return bool(c.get("enabled") and c.get("host") and c.get("from_email"))


async def send_email(store, to: str, subject: str, text: str) -> dict:
    c = _cfg(store)
    to = (to or "").strip()
    if not available(store) or not to or "@" not in to:
        return {"ok": False, "reason": "not_configured"}

    def _do():
        msg = MIMEText(text, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = c["from_email"]
        msg["To"] = to
        port = int(c.get("port") or 465)
        if str(port) == "25":
            client = smtplib.SMTP(c["host"], port, timeout=20)
        else:
            client = smtplib.SMTP_SSL(c["host"], port, timeout=20)
        try:
            if c.get("user"):
                client.login(c["user"], c.get("password") or "")
            client.sendmail(c["from_email"], [to], msg.as_string())
        finally:
            client.quit()

    try:
        await asyncio.to_thread(_do)
        return {"ok": True}
    except Exception as e:
        log.warning("email %s: %s", to, e)
        return {"ok": False, "error": str(e)[:200]}
