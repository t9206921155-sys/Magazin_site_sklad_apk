"""Автопостинг товаров в соцсети и Telegram-каналы.

Источники (настройки в админке — Настройки → Автопостинг):
  - Telegram-канал (бот должен быть админом канала)
  - VK (группа + access token с правами wall, photos)

При создании товара в админке (или в боте) вызывается post_product() —
если автопостинг включён, товар уходит во все настроенные каналы.
"""
import asyncio
import logging
import os
import re

import requests

import config

log = logging.getLogger("shop.autopost")


def public_base() -> str:
    return config.WEBAPP_URL or ""


def absolute_image_url(photo: str, base: str) -> str:
    if not photo:
        return ""
    if photo.startswith("http"):
        return photo
    return (base or "").rstrip("/") + photo


def _cfg(store) -> dict:
    return (store.settings.get("social") or {})


def caption_for(product: dict, shop_name: str, link: str = "") -> str:
    lines = [f"🛍 {product['name']}"]
    if product.get("old_price") and product["old_price"] > product["price"]:
        lines.append(f"💸 {product['old_price']} ₽ → {product['price']} ₽ (скидка!)")
    else:
        lines.append(f"💰 {product['price']} ₽")
    if product.get("description"):
        lines.append("")
        lines.append(product["description"][:220])
    lines.append("")
    lines.append(f"Заказать в {shop_name}: {link}" if link else f"Заказать в {shop_name} 👇")
    return "\n".join(lines)


def photo_path(product: dict) -> str:
    p = product.get("photo") or ""
    if p.startswith("/webapp/"):
        return os.path.join(config.WEBAPP_DIR, p.split("/webapp/", 1)[1])
    if p.startswith(("http://", "https://")):
        return p
    return ""


# ---------------------------------------------------------------- Telegram
async def post_to_telegram(bot, product: dict, channel: str, shop_name: str, link: str):
    """Пост с фото в Telegram-канал. bot — экземпляр aiogram Bot (может быть None)."""
    if not bot:
        return {"ok": False, "error": "Бот не запущен (нет BOT_TOKEN)"}
    path = photo_path(product)
    if not path:
        return {"ok": False, "error": "Нет фото у товара"}
    caption = caption_for(product, shop_name, link)
    try:
        if path.startswith("http"):
            await bot.send_photo(channel, photo=path, caption=caption)
        else:
            from aiogram.types import FSInputFile
            await bot.send_photo(channel, photo=FSInputFile(path), caption=caption)
        return {"ok": True}
    except Exception as e:
        log.warning("Автопостинг Telegram: %s", e)
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------- VK
def _vk_call(method: str, params: dict, token: str) -> dict:
    params = {**params, "v": "5.199", "access_token": token}
    r = requests.post(f"https://api.vk.com/method/{method}", data=params, timeout=30)
    data = r.json()
    if data.get("error"):
        raise ValueError(f"VK {method}: {data['error'].get('error_msg', data['error'])}")
    return data.get("response", data)


def _post_instagram(token: str, ig_user_id: str, image_url: str, caption: str) -> dict:
    """Публикация в Instagram через Graph API (business account).
    Шаг 1: create media container со ссылкой на фото. Шаг 2: publish."""
    r = requests.post(
        f"https://graph.facebook.com/v19.0/{ig_user_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token}, timeout=40)
    data = r.json()
    if r.status_code >= 300:
        raise ValueError(str(data.get("error", {}).get("message", data))[:200])
    creation_id = data.get("id")
    if not creation_id:
        raise ValueError("Instagram не вернул creation_id")
    r2 = requests.post(
        f"https://graph.facebook.com/v19.0/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token}, timeout=40)
    data2 = r2.json()
    if r2.status_code >= 300:
        raise ValueError(str(data2.get("error", {}).get("message", data2))[:200])
    return {"ok": True, "media_id": data2.get("id")}


def post_to_vk(product: dict, group_id: str, token: str, shop_name: str, link: str) -> dict:
    """Публикация записи с фото в группе VK (photos.getWallUploadServer → wall.post)."""
    path = photo_path(product)
    if not path:
        return {"ok": False, "error": "Нет фото у товара"}
    gid = str(group_id).lstrip("-")
    server = _vk_call("photos.getWallUploadServer", {"group_id": int(gid)}, token)
    with open(path, "rb") if not path.startswith("http") else _http_open(path) as f:
        r = requests.post(server["upload_url"], files={"photo": ("photo.jpg", f.read())}, timeout=60)
    up = r.json()
    saved = _vk_call("photos.saveWallPhoto", {
        "group_id": int(gid), "photo": up["photo"], "server": up["server"], "hash": up["hash"]}, token)
    photo = saved[0]
    att = f"photo{photo['owner_id']}_{photo['id']}"
    _vk_call("wall.post", {
        "owner_id": -int(gid), "from_group": 1, "attachments": att,
        "message": caption_for(product, shop_name, link)}, token)
    return {"ok": True}


class _http_open:
    """Контекстный менеджер для чтения фото по URL."""

    def __init__(self, url):
        self.url = url
        self.resp = None

    def __enter__(self):
        self.resp = requests.get(self.url, timeout=30, stream=True)
        self.resp.raise_for_status()
        return self.resp.raw

    def __exit__(self, *args):
        if self.resp:
            self.resp.close()


# ---------------------------------------------------------------- точка входа
async def post_product(store, product: dict, bot=None, force: bool = False,
                        platform: str = "") -> dict:
    """Автопостинг товара. force=True — публиковать, даже если автопостинг выключен.
    platform — публиковать только в одну площадку (telegram|vk|instagram|avito)."""
    cfg = _cfg(store)
    if not cfg.get("auto_post_new") and not force:
        return {"skipped": True}
    only = (platform or "").strip()
    shop = store.settings["shop_name"]
    link = (config.WEBAPP_URL or f"http://localhost:{config.PORT}") + f"/p/{product['id']}"
    out = {}

    channel = (cfg.get("telegram_channel") or "").strip() if not only or only == "telegram" else ""
    if channel:
        if bot is None:
            out["telegram"] = {"ok": False, "error": "Бот не запущен"}
        else:
            out["telegram"] = await post_to_telegram(bot, product, channel, shop, link)
            await asyncio.sleep(0.3)

    token = (cfg.get("vk_token") or "").strip() if not only or only == "vk" else ""
    group = (cfg.get("vk_group_id") or "").strip() if not only or only == "vk" else ""
    if token and group:
        try:
            out["vk"] = await asyncio.to_thread(post_to_vk, product, group, token, shop, link)
        except Exception as e:
            log.warning("Автопостинг VK: %s", e)
            out["vk"] = {"ok": False, "error": str(e)}

    # Instagram: Graph API (если есть токен) или готовый контент для ручной публикации
    ig_token = (cfg.get("instagram_token") or "").strip() if not only or only == "instagram" else ""
    ig_uid = (cfg.get("instagram_user_id") or "").strip() if not only or only == "instagram" else ""
    ig_caption = caption_for(product, shop, link)
    ig_tags = " ".join(f"#{t}" for t in re.findall(r"[А-Яа-яЁёA-Za-z0-9]+", product["name"].lower()))[:80]
    if ig_token and ig_uid:
        try:
            out["instagram"] = await asyncio.to_thread(
                _post_instagram, ig_token, ig_uid,
                absolute_image_url(product.get("photo") or "", public_base()),
                f"{ig_caption}\n\n{ig_tags}")
        except Exception as e:
            log.warning("Instagram: %s", e)
            out["instagram"] = {"ok": False, "error": str(e)[:200],
                                "caption": ig_caption + "\n\n" + ig_tags}
    else:
        out["instagram"] = {"ok": False, "ready": True,
                            "caption": ig_caption + "\n\n" + ig_tags,
                            "hint": "Токен Instagram не настроен — текст и фото готовы для ручной публикации."}

    av = (store.settings.get("avito") or {})
    if av.get("enabled") and av.get("auto_post_new") and (not only or only == "avito"):
        import avito as avito_module
        try:
            out["avito"] = await asyncio.to_thread(avito_module.post_to_avito, store, product)
        except Exception as e:
            log.warning("Автопостинг Avito: %s", e)
            out["avito"] = {"ok": False, "error": str(e)}
    return out
