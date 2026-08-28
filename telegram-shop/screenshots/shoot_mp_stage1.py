#!/usr/bin/env python3
"""Скриншоты Этапа 1 маркетплейса + быстрого входа склада."""
import asyncio, os
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "screenshots")

async def shot(page, path, wait=700):
    await page.wait_for_timeout(wait)
    await page.screenshot(path=os.path.join(OUT, path))
    print("OK:", path)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900},
                                        device_scale_factor=1.5, locale="ru-RU")
        page = await ctx.new_page()

        # 1) Сайт: товар с состоянием/параметрами/избранным
        await page.goto(BASE + "/p/10", wait_until="networkidle")
        await shot(page, "MP-PRODUCT-CONDITION-PARAMS.png", 600)
        await page.click("#fav-btn")
        await shot(page, "MP-PRODUCT-FAV.png", 400)

        # 2) Сайт: каталог ЧПУ подкатегории с SEO-текстом
        await page.goto(BASE + "/catalog/obuv/krossovki", wait_until="networkidle")
        await shot(page, "MP-CATALOG-SUBCATEGORY.png", 600)

        # 3) Сайт: избранное
        await page.goto(BASE + "/favorites", wait_until="networkidle")
        await page.wait_for_timeout(1200)
        await shot(page, "MP-FAVORITES-PAGE.png", 500)

        # 4) Админка: таб «Каталог» (подкатегории)
        await page.goto(BASE + "/admin", wait_until="networkidle")
        await page.fill("#pass", "admin123")
        await page.click("text=Войти")
        await page.wait_for_selector("#tab-dashboard:not(.hidden)", timeout=15000)
        await page.click('button[data-tab="catalog"]')
        await page.wait_for_selector("#tab-catalog:not(.hidden) #sc-cat", timeout=10000)
        await shot(page, "MP-ADMIN-CATALOG.png", 500)

        # 5) Админка: форма товара с состоянием и параметрами
        await page.click('button[data-tab="products"]')
        await page.wait_for_selector("#tab-products:not(.hidden)", timeout=10000)
        try:
            await page.click("text=Добавить товар")
            await page.wait_for_selector("#pf-cond", timeout=8000)
            await shot(page, "MP-ADMIN-PRODUCT-FORM.png", 500)
            await page.click("#pf-save")  # просто закрыть модалку через отмену ниже
        except Exception as e:
            print("форма: пропуск", e)
        try:
            await page.evaluate("document.querySelector('.modal-overlay')?.remove()")
        except Exception:
            pass

        # 6) Mini App: избранное
        await page.goto(BASE + "/app", wait_until="networkidle")
        await page.wait_for_selector("#grid .card", timeout=15000)
        await page.wait_for_timeout(800)
        await shot(page, "MP-WEBAPP-CARD-FAV.png", 400)
        try:
            await page.evaluate("openProduct(10)")
            await page.wait_for_selector("#pm.open", timeout=8000)
            await shot(page, "MP-WEBAPP-PRODUCT-PARAMS.png", 500)
        except Exception as e:
            print("webapp pm: пропуск", e)

        # 7) Склад: экран входа с быстрым входом (PIN)
        await page.goto(BASE + "/warehouse/", wait_until="networkidle")
        await page.wait_for_timeout(800)
        try:
            await page.evaluate("""localStorage.setItem('wh_quick', JSON.stringify(
                {pin:'1234', data: btoa(unescape(encodeURIComponent('test|00000'))), login:'ivan', bio:false}))""")
            await page.reload(wait_until="networkidle")
            await page.wait_for_timeout(600)
            await shot(page, "WH-QUICK-LOGIN.png", 400)
        except Exception as e:
            print("склад quick: пропуск", e)

        await browser.close()

asyncio.run(main())
