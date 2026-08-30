#!/usr/bin/env python3
"""Скриншоты для документации APK: мокап экрана настройки + реальный склад в мобильном viewport."""
import asyncio, os, sys
from playwright.async_api import async_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "..", "screenshots")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
            user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36 SkladApp/1.0.2",
            locale="ru-RU",
        )
        page = await ctx.new_page()

        # 1) Мокап экрана настройки (первый запуск приложения)
        await page.goto("file://" + os.path.join(BASE, "mock-setup-screen.html"))
        await page.wait_for_timeout(300)
        await page.screenshot(path=os.path.join(OUT, "APK-SETUP-SCREEN.png"))
        print("OK: APK-SETUP-SCREEN.png")

        # 2) Реальный склад в мобильном viewport (как он выглядит в WebView)
        try:
            await page.goto("http://127.0.0.1:8000/warehouse/", wait_until="networkidle", timeout=20000)
        except Exception as e:
            await page.goto("http://127.0.0.1:8000/warehouse/", timeout=20000)
            await page.wait_for_timeout(2500)
        await page.wait_for_timeout(1200)
        await page.screenshot(path=os.path.join(OUT, "APK-WAREHOUSE-SCREEN.png"))
        print("OK: APK-WAREHOUSE-SCREEN.png")

        await browser.close()

asyncio.run(main())
