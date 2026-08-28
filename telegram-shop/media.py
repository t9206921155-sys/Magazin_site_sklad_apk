"""Генерация рекламных материалов: баннеры (PIL) и видеоролики (ffmpeg).

Баннеры: 1080×1080 (пост) и 1200×628 (OG-картинка для соцсетей).
Видео: слайд-шоу из фото товара с титрами, зумом и переходами — 10 сек, 1080×1080.
Всё кладётся в data/media/ и раздаётся по /media/...
"""
import logging
import os
import re
import subprocess
import textwrap
import uuid

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config

log = logging.getLogger("shop.media")

MEDIA_DIR = os.path.join(config.DATA_DIR, "media")
BANNERS_DIR = os.path.join(MEDIA_DIR, "banners")
VIDEOS_DIR = os.path.join(MEDIA_DIR, "videos")
os.makedirs(BANNERS_DIR, exist_ok=True)
os.makedirs(VIDEOS_DIR, exist_ok=True)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

GRADIENTS = {
    "indigo": ((79, 70, 229), (124, 58, 237)),
    "ocean": ((2, 132, 199), (45, 212, 191)),
    "sunset": ((249, 115, 22), (239, 68, 68)),
    "forest": ((5, 150, 105), (132, 204, 22)),
}


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold and os.path.exists(FONT_BOLD) else FONT_REG
    if not os.path.exists(path):
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


def _gradient(w: int, h: int, colors) -> Image.Image:
    base = Image.new("RGB", (w, h))
    top, bottom = colors
    for y in range(h):
        t = y / max(1, h - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        base.paste(c, (0, y, w, y + 1))
    return base


def _open_photo(product: dict) -> Image.Image:
    p = product.get("photo") or ""
    if p.startswith("/webapp/"):
        path = os.path.join(config.WEBAPP_DIR, p.split("/webapp/", 1)[1])
        return Image.open(path).convert("RGB")
    if p.startswith(("http://", "https://")):
        import io
        import requests
        r = requests.get(p, timeout=20)
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    return Image.new("RGB", (600, 600), (226, 228, 232))


def _rounded(im: Image.Image, radius: int) -> tuple:
    """Возвращает (изображение, маска скругления)."""
    mask = Image.new("L", im.size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, im.size[0] - 1, im.size[1] - 1], radius=radius, fill=255)
    return im, mask


def _fit_cover(src: Image.Image, w: int, h: int) -> Image.Image:
    sw, sh = src.size
    scale = max(w / sw, h / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    src = src.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - w) // 2, (nh - h) // 2
    return src.crop((x, y, x + w, y + h))


def generate_banner(product: dict, shop_name: str, size=(1080, 1080), gradient="indigo") -> str:
    """Рекламный баннер 1080×1080: фото товара, название, цена, скидка, CTA."""
    w, h = size
    img = _gradient(w, h, GRADIENTS.get(gradient, GRADIENTS["indigo"]))

    photo = _fit_cover(_open_photo(product), int(w * 0.72), int(h * 0.72))
    photo, photo_mask = _rounded(photo, 40)
    photo = photo.filter(ImageFilter.SMOOTH)
    img.paste(photo, ((w - photo.size[0]) // 2, int(h * 0.05)), photo_mask)

    d = ImageDraw.Draw(img)
    name = re.sub(r"\s+", " ", product["name"])
    name = name[:80]
    font_name = _font(46)
    lines = textwrap.wrap(name, width=24)
    y = int(h * 0.80)
    for line in lines[:2]:
        bbox = d.textbbox((0, 0), line, font=font_name)
        d.text(((w - (bbox[2] - bbox[0])) // 2, y), line, font=font_name, fill=(255, 255, 255))
        y += bbox[3] - bbox[1] + 6

    if product.get("old_price") and product["old_price"] > product["price"]:
        font_old = _font(40, bold=False)
        font_price = _font(64)
        old = f"{product['old_price']} ₽"
        price = f"{product['price']} ₽"
        b1 = d.textbbox((0, 0), old, font=font_old)
        b2 = d.textbbox((0, 0), price, font=font_price)
        total = (b1[2] - b1[0]) + 24 + (b2[2] - b2[0])
        x = (w - total) // 2
        py = y + 10
        d.text((x, py), old, font=font_old, fill=(255, 255, 255, 200))
        d.line((x, py + (b1[3] - b1[1]) // 2, x + (b1[2] - b1[0]),
                py + (b1[3] - b1[1]) // 2), fill=(255, 80, 80), width=4)
        d.text((x + (b1[2] - b1[0]) + 24, py - 12), price, font=font_price, fill=(255, 255, 255))
    else:
        font_price = _font(58)
        price = f"{product['price']} ₽"
        b2 = d.textbbox((0, 0), price, font=font_price)
        d.text(((w - (b2[2] - b2[0])) // 2, y + 8), price, font=font_price, fill=(255, 255, 255))

    badge = "🔥 СКИДКА" if product.get("old_price") and product["old_price"] > product["price"] else "⭐ НОВИНКА"
    font_badge = _font(26)
    bbox = d.textbbox((0, 0), badge, font=font_badge)
    pad = 20
    d.rounded_rectangle([24, 24, 24 + (bbox[2] - bbox[0]) + pad * 2, 24 + (bbox[3] - bbox[1]) + pad],
                        radius=22, fill=(255, 255, 255, 230))
    d.text((24 + pad, 24 + pad // 2), badge, font=font_badge, fill=(30, 30, 40))

    cta = f"🛍 {shop_name}"
    font_cta = _font(24)
    bbox = d.textbbox((0, 0), cta, font=font_cta)
    d.text(((w - (bbox[2] - bbox[0])) // 2, h - 74), cta, font=font_cta, fill=(255, 255, 255, 220))

    fname = f"{product['id']}_{uuid.uuid4().hex[:6]}_{w}x{h}.jpg"
    path = os.path.join(BANNERS_DIR, fname)
    img.save(path, quality=92)
    return f"/media/banners/{fname}"


def generate_og_image(product: dict, shop_name: str) -> str:
    """OG-картинка 1200×628 для соцсетей и поисковиков."""
    return generate_banner(product, shop_name, size=(1200, 628), gradient="ocean")


def generate_video(product: dict, shop_name: str, seconds: int = 10) -> str:
    """Видеоролик 1080×1080: фото товара с зумом и титрами (ffmpeg)."""
    w, h = 1080, 1080
    fps = 25
    frames_dir = os.path.join(VIDEOS_DIR, f"tmp_{uuid.uuid4().hex[:8]}")
    os.makedirs(frames_dir, exist_ok=True)
    try:
        photo = _fit_cover(_open_photo(product), w, h)
        n = seconds * fps
        import math
        for i in range(n):
            t = i / n
            # плавный зум 1.0 -> 1.18
            zoom = 1.0 + 0.18 * t
            nw, nh = int(w * zoom), int(h * zoom)
            frame = photo.resize((nw, nh), Image.LANCZOS)
            x = int((nw - w) * (0.5 + 0.15 * math.sin(t * math.pi)))  # лёгкое панорамирование
            y = (nh - h) // 2
            frame = frame.crop((x, y, x + w, y + h)).filter(ImageFilter.SMOOTH)
            # титры
            d = ImageDraw.Draw(frame)
            overlay = Image.new("RGBA", (w, 300), (0, 0, 0, 130))
            frame_rgba = frame.convert("RGBA")
            frame_rgba.paste(overlay, (0, h - 300), overlay)
            frame = frame_rgba.convert("RGB")
            d = ImageDraw.Draw(frame)
            name = re.sub(r"\s+", " ", product["name"])[:60]
            for j, line in enumerate(textwrap.wrap(name, width=22)[:2]):
                f = _font(52)
                bbox = d.textbbox((0, 0), line, font=f)
                d.text(((w - (bbox[2] - bbox[0])) // 2, h - 280 + j * 74), line, font=f, fill=(255, 255, 255))
            price = f"{product['price']} ₽"
            if product.get("old_price") and product["old_price"] > product["price"]:
                price = f"{product['old_price']} ₽ → {product['price']} ₽"
            f = _font(46)
            bbox = d.textbbox((0, 0), price, font=f)
            d.text(((w - (bbox[2] - bbox[0])) // 2, h - 128), price, font=f, fill=(255, 224, 130))
            f = _font(28)
            cta = f"🛍 {shop_name}"
            bbox = d.textbbox((0, 0), cta, font=f)
            d.text(((w - (bbox[2] - bbox[0])) // 2, h - 60), cta, font=f, fill=(255, 255, 255, 220))
            frame.save(os.path.join(frames_dir, f"f{i:05d}.png"))

        fname = f"{product['id']}_{uuid.uuid4().hex[:6]}.mp4"
        out_path = os.path.join(VIDEOS_DIR, fname)
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [ffmpeg, "-y", "-framerate", str(fps),
               "-i", os.path.join(frames_dir, "f%05d.png"),
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-movflags", "+faststart",
               "-t", str(seconds), out_path]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr[-400:])
        return f"/media/videos/{fname}"
    finally:
        import shutil
        shutil.rmtree(frames_dir, ignore_errors=True)
