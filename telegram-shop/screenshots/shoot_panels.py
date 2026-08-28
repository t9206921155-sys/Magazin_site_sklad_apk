"""Скриншоты: админ-панель площадки + кабинет продавца."""
import os
import time

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
OUT = os.path.dirname(os.path.abspath(__file__))
SKEY = open("/tmp/skey.txt").read().strip()


def shot(page, name, full=False):
    page.screenshot(path=os.path.join(OUT, name), full_page=full)
    print("saved:", name)


with sync_playwright() as p:
    browser = p.chromium.launch()

    # ============ АДМИН-ПАНЕЛЬ ПЛОЩАДКИ ============
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/admin/", wait_until="networkidle")
    time.sleep(0.6)
    page.fill("#pass", "admin123")
    page.click('button:has-text("Войти")')
    time.sleep(1.4)

    shot(page, "ad01-dashboard.png")
    page.click('button[data-tab="sellers"]')
    time.sleep(0.9)
    shot(page, "ad02-sellers.png")
    page.click('button[data-tab="orders"]')
    time.sleep(0.9)
    shot(page, "ad03-orders.png")
    page.click('button[data-tab="settings"]')
    time.sleep(0.9)
    page.evaluate('document.getElementById("mp-en").scrollIntoView({block:"center"})')
    time.sleep(0.4)
    shot(page, "ad04-settings-marketplace.png")
    page.click('button[data-tab="promos"]')
    time.sleep(0.9)
    shot(page, "ad05-promos.png")
    ctx.close()

    # ============ КАБИНЕТ ПРОДАВЦА ============
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/seller/", wait_until="networkidle")
    time.sleep(0.7)
    page.evaluate("key => localStorage.setItem('tgshop_seller_key', key)", SKEY)
    page.reload()
    time.sleep(1.5)

    shot(page, "se01-dashboard.png")
    page.click('button[data-tab="products"]')
    time.sleep(0.9)
    shot(page, "se02-products.png")
    page.click('button[data-tab="promos"]')
    time.sleep(0.9)
    shot(page, "se03-promos.png")
    page.click('button[data-tab="orders"]')
    time.sleep(0.9)
    shot(page, "se04-orders.png")
    page.click('button[data-tab="payouts"]')
    time.sleep(0.9)
    shot(page, "se05-payouts.png")
    page.click('button[data-tab="settings"]')
    time.sleep(0.9)
    shot(page, "se06-settings.png")
    ctx.close()

    browser.close()
    print("DONE")
