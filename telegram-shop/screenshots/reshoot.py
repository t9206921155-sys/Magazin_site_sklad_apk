"""Пересъёмка скриншотов с новыми блоками: 5POST и Т-Банк."""
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

    # Админка: настройки (новые секции 5POST и Т-Банк)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/admin/", wait_until="networkidle")
    time.sleep(0.6)
    page.fill("#pass", "admin123")
    page.click('button:has-text("Войти")')
    time.sleep(1.2)
    page.click('button[data-tab="settings"]')
    time.sleep(1.0)
    shot(page, "14-admin-settings.png", full=True)
    ctx.close()

    # Сайт: корзина с выбранным 5POST
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = ctx.new_page()
    page.goto(BASE + "/#/catalog", wait_until="networkidle")
    time.sleep(0.6)
    page.click(".card:nth-child(1) .add-btn")
    time.sleep(0.4)
    page.goto(BASE + "/#/cart", wait_until="networkidle")
    time.sleep(0.6)
    page.fill("#f-name", "Пётр Иванов")
    page.fill("#f-phone", "+7 903 000-11-22")
    page.fill("#f-city", "Москва")
    # выбор 5POST
    page.click('input[name="dm"][value="fivepost"]')
    time.sleep(1.2)
    shot(page, "16-site-cart-fivepost.png", full=True)
    ctx.close()

    # Mini App: оформление с 5POST
    ctx = browser.new_context(viewport={"width": 393, "height": 852}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(BASE + "/app/", wait_until="networkidle")
    time.sleep(1.0)
    page.click(".card:nth-child(1) .plus")
    time.sleep(0.4)
    page.click('#cart-bar [data-action="checkout"]')
    time.sleep(0.6)
    page.fill("#co-name", "Анна Смирнова")
    page.fill("#co-phone", "+7 912 345-67-89")
    page.fill("#co-city", "Москва")
    # выбор 5POST
    page.click('.drow[data-id="fivepost"]')
    time.sleep(1.2)
    shot(page, "17-miniapp-checkout-fivepost.png")
    ctx.close()

    browser.close()
    print("DONE")
