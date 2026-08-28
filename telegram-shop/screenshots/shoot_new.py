"""Скриншоты новых функций: бейджи/скидки, промокоды, отчёты, настройки."""
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

    # Сайт: каталог с бейджами и скидками
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/#/catalog", wait_until="networkidle")
    time.sleep(1.0)
    shot(page, "18-site-catalog-badges.png")

    # Сайт: товар со скидкой
    page.goto(BASE + "/#/p/4", wait_until="networkidle")
    time.sleep(0.8)
    shot(page, "19-site-product-discount.png")

    # Сайт: корзина с промокодом и бесплатной доставкой
    page.goto(BASE + "/#/catalog", wait_until="networkidle")
    time.sleep(0.6)
    page.click(".card:nth-child(2) .add-btn")
    time.sleep(0.3)
    page.goto(BASE + "/#/cart", wait_until="networkidle")
    time.sleep(0.6)
    page.fill("#f-name", "Пётр Иванов")
    page.fill("#f-phone", "+7 903 000-11-22")
    page.fill("#f-city", "Москва")
    page.fill("#f-address", "ул. Арбат, 10")
    page.fill("#f-promo", "SALE20")
    page.click("#promo-btn")
    time.sleep(1.0)
    shot(page, "20-site-cart-promo.png", full=True)
    ctx.close()

    # Mini App: товар со скидкой
    ctx = browser.new_context(viewport={"width": 393, "height": 852}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(BASE + "/app/", wait_until="networkidle")
    time.sleep(1.0)
    page.click(".card:nth-child(4)")  # термокружка со скидкой
    time.sleep(0.8)
    shot(page, "21-miniapp-product-discount.png")
    page.click('[data-action="pm-add"]')
    time.sleep(0.4)
    page.click('#cart-bar [data-action="checkout"]')
    time.sleep(0.7)
    page.fill("#co-name", "Анна Смирнова")
    page.fill("#co-phone", "+7 912 345-67-89")
    page.fill("#co-address", "Ленинский проспект, 42")
    page.fill("#co-promo", "SALE20")
    page.click('[data-action="promo-apply"]')
    time.sleep(1.0)
    shot(page, "22-miniapp-checkout-promo.png")
    ctx.close()

    # Админка: промокоды
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/admin/", wait_until="networkidle")
    time.sleep(0.6)
    page.fill("#pass", "admin123")
    page.click('button:has-text("Войти")')
    time.sleep(1.4)
    page.click('button[data-tab="promos"]')
    time.sleep(0.9)
    shot(page, "23-admin-promos.png")

    # Админка: отчёты
    page.click('button[data-tab="reports"]')
    time.sleep(0.9)
    shot(page, "24-admin-reports.png", full=True)

    # Админка: рассылка
    page.click('button[data-tab="broadcast"]')
    time.sleep(0.9)
    shot(page, "25-admin-broadcast.png")
    ctx.close()

    browser.close()
    print("DONE")
