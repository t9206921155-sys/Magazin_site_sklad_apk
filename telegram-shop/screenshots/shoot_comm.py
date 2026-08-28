"""Скриншоты: комиссия, Excel/1С, страница «Сдать вещь»."""
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

    # Админка: комиссия
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/admin/", wait_until="networkidle")
    time.sleep(0.6)
    page.fill("#pass", "admin123")
    page.click('button:has-text("Войти")')
    time.sleep(1.4)
    page.click('button[data-tab="commission"]')
    time.sleep(1.0)
    shot(page, "60-admin-commission.png", full=True)

    # Админка: Импорт · Excel · 1С (с проверкой связи)
    page.click('button[data-tab="import"]')
    time.sleep(0.9)
    page.click('button:has-text("Проверить связь с 1С")')
    time.sleep(1.0)
    shot(page, "61-admin-import-excel-1c.png", full=True)
    ctx.close()

    # Сайт: страница «Сдать вещь»
    ctx = browser.new_context(viewport={"width": 1440, "height": 940})
    page = ctx.new_page()
    page.goto(BASE + "/commission", wait_until="networkidle")
    time.sleep(0.8)
    shot(page, "62-commission-page.png", full=True)

    # Сайт: карточка комиссионного товара с бейджем
    page.goto(BASE + "/catalog", wait_until="networkidle")
    time.sleep(0.7)
    shot(page, "63-catalog-commission-badge.png")
    # находим комиссионный товар
    page.goto(BASE + "/p/11", wait_until="networkidle")
    time.sleep(0.8)
    shot(page, "64-commission-product.png")
    ctx.close()

    browser.close()
    print("DONE")
