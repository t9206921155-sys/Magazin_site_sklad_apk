#!/usr/bin/env python3
"""Скриншоты новых функций: тарифы, кабинет продавца, чаты, массовое редактирование."""
import asyncio, os
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "screenshots")

async def shot(page, path, wait=800):
    await page.wait_for_timeout(wait)
    await page.screenshot(path=os.path.join(OUT, path))
    print("OK:", path)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900},
                                        device_scale_factor=1.5, locale="ru-RU")
        page = await ctx.new_page()

        # 1) Админка: тарифы
        await page.goto(BASE + "/admin", wait_until="networkidle")
        await page.fill("#pass", "admin123")
        await page.click("text=Войти")
        await page.wait_for_selector("#tab-dashboard:not(.hidden)", timeout=15000)
        await page.click('button[data-tab="tariffs"]')
        await page.wait_for_selector("#tab-tariffs:not(.hidden) #t-commission", timeout=10000)
        await shot(page, "TARIFFS-ADMIN.png", 500)

        # 2) Админка: продавцы (тариф/холд/верификация)
        await page.click('button[data-tab="sellers"]')
        await page.wait_for_selector("#tab-sellers:not(.hidden) table", timeout=10000)
        await shot(page, "SELLERS-ADMIN-PLAN-VERIFY.png", 500)

        # 3) Кабинет продавца: дашборд с тарифом
        await page.goto(BASE + "/seller", wait_until="networkidle")
        await page.fill("#key", "b519201bb5a533540e7449a03ffbc97a")
        await page.click("text=Войти")
        await page.wait_for_selector("#tab-dashboard:not(.hidden)", timeout=15000)
        await shot(page, "SELLER-DASHBOARD-TARIFF.png", 800)

        # 4) Кабинет продавца: чат
        await page.click('button[data-tab="chat"]')
        await page.wait_for_selector("#tab-chat:not(.hidden)", timeout=10000)
        await shot(page, "SELLER-CHAT.png", 800)

        # 5) Mini App: товар с кнопкой чата
        await page.goto(BASE + "/app", wait_until="networkidle")
        await page.wait_for_selector(".card, .b-card, article", timeout=15000)
        # открываем товар продавца (браслет id 9)
        try:
            await page.evaluate("openProduct(9)")
        except Exception:
            pass
        await page.wait_for_selector("#pm.open", timeout=10000)
        await shot(page, "WEBAPP-PRODUCT-CHAT-BTN.png", 500)
        await page.click("#pm-chat")
        await page.wait_for_selector("#chat.open", timeout=10000)
        await shot(page, "WEBAPP-CHAT.png", 800)

        # 6) Сайт: страница товара с чат-панелью
        await page.goto(BASE + "/p/9", wait_until="networkidle")
        try:
            await page.click("#chat-open-btn")
            await page.wait_for_timeout(800)
        except Exception:
            pass
        await shot(page, "SITE-PRODUCT-CHAT.png", 500)

        # 7) Склад: массовое редактирование
        await page.goto(BASE + "/warehouse/", wait_until="networkidle")
        try:
            await page.fill("#login-inp", "ivan")
            await page.fill("#pass", "ivan123")
            await page.click("#login button")
            await page.wait_for_selector("#login.hidden", timeout=10000)
        except Exception:
            pass
        # отметить два товара
        await page.wait_for_timeout(1000)
        try:
            boxes = await page.query_selector_all(".chk")
            for b in boxes[:2]:
                await b.check()
            await page.wait_for_timeout(400)
            await page.click("#bulkBtn")
            await page.wait_for_selector("#sheet3:not(.hidden)", timeout=8000)
            await page.fill("#bk-location", "Б-2 стеллаж")
            await shot(page, "WAREHOUSE-BULK-EDIT.png", 400)
            await page.click("#sheet3 .btn.ghost")
        except Exception as e:
            print("склад bulk: пропуск", e)

        await browser.close()

asyncio.run(main())
