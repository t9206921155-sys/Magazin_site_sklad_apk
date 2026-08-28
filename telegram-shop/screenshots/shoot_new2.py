"""Скриншоты: отзывы, блог, бонусы, админка."""
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

    # Карточка товара с отзывами
    ctx = browser.new_context(viewport={"width": 1440, "height": 940})
    page = ctx.new_page()
    page.goto(BASE + "/p/4", wait_until="networkidle")
    time.sleep(0.8)
    page.evaluate("document.getElementById('reviews').scrollIntoView()")
    time.sleep(0.4)
    shot(page, "50-product-reviews.png")

    # Блог: список
    page.goto(BASE + "/blog", wait_until="networkidle")
    time.sleep(0.8)
    shot(page, "51-blog-list.png", full=True)

    # Блог: статья
    page.goto(BASE + "/blog/kak-vybrat-naushniki", wait_until="networkidle")
    time.sleep(0.8)
    shot(page, "52-blog-post.png", full=True)
    ctx.close()

    # Корзина с бонусами (сайт)
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = ctx.new_page()
    page.goto(BASE + "/shop#/cart", wait_until="networkidle")
    time.sleep(0.7)
    page.evaluate("""localStorage.setItem('tgshop_guest', 'loy-test'); localStorage.setItem('tgshop_cart', JSON.stringify({"4":1}))""")
    page.reload()
    time.sleep(0.9)
    page.fill("#f-name", "Лояльный Клиент")
    page.fill("#f-phone", "+7 900 111-00-00")
    page.fill("#f-city", "Москва")
    page.fill("#f-address", "ул. Бонусная, 5")
    time.sleep(0.6)
    if page.locator("#f-bonus-check").count():
        page.check("#f-bonus-check")
        time.sleep(0.6)
    shot(page, "53-cart-bonus.png", full=True)
    ctx.close()

    # Админка: отзывы
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/admin/", wait_until="networkidle")
    time.sleep(0.6)
    page.fill("#pass", "admin123")
    page.click('button:has-text("Войти")')
    time.sleep(1.4)
    page.click('button[data-tab="reviews"]')
    time.sleep(0.9)
    shot(page, "54-admin-reviews.png")

    # Админка: блог
    page.click('button[data-tab="blog"]')
    time.sleep(0.9)
    shot(page, "55-admin-blog.png")
    ctx.close()

    browser.close()
    print("DONE")
