"""Скриншоты всех интерфейсов магазина (Playwright). Запуск: python make_shots.py"""
import os
import time

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
OUT = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUT, exist_ok=True)


def shot(page, name, full=False):
    page.screenshot(path=os.path.join(OUT, name), full_page=full)
    print("saved:", name)


with sync_playwright() as p:
    browser = p.chromium.launch()

    # ============ Mini App (мобильный) ============
    ctx = browser.new_context(viewport={"width": 393, "height": 852}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(BASE + "/app/", wait_until="networkidle")
    time.sleep(1.2)
    shot(page, "01-miniapp-catalog.png")

    page.click(".card:nth-child(1)")
    time.sleep(0.7)
    shot(page, "02-miniapp-product.png")
    page.click('[data-action="pm-add"]')
    time.sleep(0.4)
    page.click('[data-action="cart-open"]')
    time.sleep(0.7)
    shot(page, "03-miniapp-cart.png")
    page.click('[data-action="checkout"]')
    time.sleep(0.6)
    page.fill("#co-name", "Анна Смирнова")
    page.fill("#co-phone", "+7 912 345-67-89")
    page.fill("#co-city", "Москва")
    page.fill("#co-address", "Ленинский проспект, 42, кв. 7")
    time.sleep(0.3)
    shot(page, "04-miniapp-checkout.png")
    page.click('[data-action="co-submit"]')
    time.sleep(1.4)
    shot(page, "05-miniapp-payment.png")
    page.click('[data-action="pay-now"]')
    time.sleep(2.6)
    shot(page, "06-miniapp-success.png")
    ctx.close()

    # ============ Сайт (десктоп) ============
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/", wait_until="networkidle")
    time.sleep(1.2)
    shot(page, "07-site-home.png", full=True)

    page.goto(BASE + "/#/catalog", wait_until="networkidle")
    time.sleep(0.8)
    page.fill("#search", "часы")
    time.sleep(0.4)
    shot(page, "08-site-catalog.png")

    page.goto(BASE + "/#/p/2", wait_until="networkidle")
    time.sleep(0.8)
    shot(page, "09-site-product.png")

    page.goto(BASE + "/#/catalog", wait_until="networkidle")
    time.sleep(0.6)
    page.click(".card:nth-child(1) .add-btn")
    time.sleep(0.4)
    page.goto(BASE + "/#/cart", wait_until="networkidle")
    time.sleep(0.6)
    page.fill("#f-name", "Пётр Иванов")
    page.fill("#f-phone", "+7 903 000-11-22")
    page.fill("#f-city", "Москва")
    page.fill("#f-address", "ул. Арбат, 10")
    time.sleep(0.3)
    shot(page, "10-site-cart.png", full=True)
    ctx.close()

    # ============ Админ-панель ============
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/admin/", wait_until="networkidle")
    time.sleep(0.8)
    shot(page, "11-admin-login.png")
    page.fill("#pass", "admin123")
    page.click('button:has-text("Войти")')
    time.sleep(1.5)
    shot(page, "12-admin-dashboard.png")
    page.click('button[data-tab="products"]')
    time.sleep(0.9)
    shot(page, "13-admin-products.png")
    page.click('button[data-tab="settings"]')
    time.sleep(0.9)
    shot(page, "14-admin-settings.png", full=True)
    page.click('button[data-tab="import"]')
    time.sleep(0.9)
    shot(page, "15-admin-import.png", full=True)
    ctx.close()

    browser.close()
    print("DONE")
