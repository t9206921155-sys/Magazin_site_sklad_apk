"""Скриншоты нового сайта: десктоп + мобильный."""
import os
import time

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
OUT = os.path.dirname(os.path.abspath(__file__))


def shot(page, name, full=False):
    page.screenshot(path=os.path.join(OUT, name), full_page=full)
    print("saved:", name)


with sync_playwright() as p:
    browser = p.chromium.launch()

    # Десктоп
    ctx = browser.new_context(viewport={"width": 1440, "height": 940})
    page = ctx.new_page()
    page.goto(BASE + "/", wait_until="networkidle")
    time.sleep(1.0)
    shot(page, "30-site-home-new.png", full=True)

    page.goto(BASE + "/catalog", wait_until="networkidle")
    time.sleep(0.8)
    shot(page, "31-site-catalog-new.png", full=True)

    page.goto(BASE + "/p/4", wait_until="networkidle")
    time.sleep(0.8)
    shot(page, "32-site-product-new.png", full=True)

    # Баннер
    page.goto(BASE + "/media/banners/4_a281db_1080x1080.jpg", wait_until="networkidle")
    time.sleep(0.5)
    shot(page, "33-banner-example.png")
    ctx.close()

    # Мобильный
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.goto(BASE + "/", wait_until="networkidle")
    time.sleep(1.0)
    shot(page, "34-mobile-home.png", full=True)

    page.goto(BASE + "/p/1", wait_until="networkidle")
    time.sleep(0.8)
    shot(page, "35-mobile-product.png", full=True)

    # мобильное меню
    page.goto(BASE + "/", wait_until="networkidle")
    time.sleep(0.8)
    page.click("#burger")
    time.sleep(0.5)
    shot(page, "36-mobile-menu.png")
    ctx.close()

    browser.close()
    print("DONE")
