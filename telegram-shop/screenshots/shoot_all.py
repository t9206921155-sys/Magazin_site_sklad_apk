"""Скриншоты всех страниц сайта и Telegram-витрины (Mini App)."""
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

    # ============ САЙТ (десктоп) ============
    ctx = browser.new_context(viewport={"width": 1440, "height": 940})
    page = ctx.new_page()

    page.goto(BASE + "/", wait_until="networkidle")
    time.sleep(1.2)
    shot(page, "w01-home-full.png", full=True)
    shot(page, "w01-home-top.png")

    page.click('.sl-dot[data-dot="1"]')
    time.sleep(0.9)
    shot(page, "w02-home-slide-promo.png")

    page.goto(BASE + "/catalog", wait_until="networkidle")
    time.sleep(0.9)
    shot(page, "w03-catalog.png", full=True)

    page.goto(BASE + "/p/4", wait_until="networkidle")
    time.sleep(0.9)
    shot(page, "w04-product.png", full=True)

    page.goto(BASE + "/sellers", wait_until="networkidle")
    time.sleep(0.9)
    shot(page, "w05-sellers.png", full=True)

    page.goto(BASE + "/seller/svetlana", wait_until="networkidle")
    time.sleep(0.9)
    shot(page, "w06-seller-store.png", full=True)

    page.goto(BASE + "/become-seller", wait_until="networkidle")
    time.sleep(0.9)
    shot(page, "w07-become-seller.png", full=True)

    page.goto(BASE + "/seller/", wait_until="networkidle")
    time.sleep(0.8)
    shot(page, "w08-seller-login.png")

    page.goto(BASE + "/blog", wait_until="networkidle")
    time.sleep(0.9)
    shot(page, "w09-blog.png", full=True)

    page.goto(BASE + "/shop#/cart", wait_until="networkidle")
    time.sleep(0.9)
    page.evaluate('localStorage.setItem("tgshop_cart", JSON.stringify({"1":1,"4":1}))')
    page.reload()
    time.sleep(1.0)
    shot(page, "w10-spa-cart.png", full=True)
    ctx.close()

    # ============ САЙТ (мобильный) ============
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                              is_mobile=True, has_touch=True)
    m = ctx.new_page()
    m.goto(BASE + "/", wait_until="networkidle")
    time.sleep(1.0)
    shot(m, "w11-mobile-home.png")
    m.goto(BASE + "/p/4", wait_until="networkidle")
    time.sleep(0.9)
    shot(m, "w12-mobile-product.png")
    ctx.close()

    # ============ TELEGRAM: Mini App (смартфон) ============
    ctx = browser.new_context(viewport={"width": 393, "height": 852}, device_scale_factor=2)
    t = ctx.new_page()
    t.goto(BASE + "/app/", wait_until="networkidle")
    time.sleep(1.2)
    shot(t, "t01-miniapp-catalog.png")

    t.click(".card:nth-child(4)")
    time.sleep(0.8)
    shot(t, "t02-miniapp-product.png")
    t.click('[data-action="pm-add"]')
    time.sleep(0.4)

    t.click("#cart-bar [data-action='checkout']")
    time.sleep(0.8)
    t.fill("#co-name", "Анна Смирнова")
    t.fill("#co-phone", "+7 912 345-67-89")
    t.fill("#co-city", "Москва")
    t.fill("#co-address", "Ленинский проспект, 42")
    t.fill("#co-promo", "SALE20")
    t.click('[data-action="promo-apply"]')
    time.sleep(0.8)
    shot(t, "t03-miniapp-checkout.png")

    t.click('[data-action="co-submit"]')
    time.sleep(1.4)
    shot(t, "t04-miniapp-payment.png")

    t.click('.drow[data-id="transfer"]')
    time.sleep(0.9)
    shot(t, "t05-miniapp-transfer.png")

    t.click('[data-action="pay-now"]')
    time.sleep(1.6)
    shot(t, "t06-miniapp-paid-wait.png")
    ctx.close()

    # ============ TELEGRAM: бот (имитация чата) ============
    ctx = browser.new_context(viewport={"width": 393, "height": 852}, device_scale_factor=2)
    b = ctx.new_page()
    html = """<html><head><meta charset="utf-8"><style>
      body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;background:#0e1621;color:#fff}
      .chat{max-width:420px;margin:0 auto;padding:14px 12px;background-image:linear-gradient(rgba(14,22,33,.9),rgba(14,22,33,.9));}
      .hdr{position:sticky;top:0;display:flex;align-items:center;gap:10px;background:#17212b;padding:10px 12px;border-radius:0 0 0 0;margin:-14px -12px 12px}
      .ava{width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,#4f46e5,#7c3aed);display:flex;align-items:center;justify-content:center;font-size:19px}
      .nm b{display:block;font-size:14px}.nm span{font-size:12px;color:#6c7883}
      .msg{max-width:85%;margin-bottom:10px;padding:9px 12px;border-radius:14px;font-size:14px;line-height:1.45}
      .bot{background:#17212b;border-top-left-radius:4px}
      .user{background:#4f46e5;margin-left:auto;border-top-right-radius:4px}
      .kb{max-width:88%;margin-bottom:12px}
      .btn{display:block;background:#17212b;border-radius:12px;padding:10px 14px;font-size:14px;margin-top:6px;text-align:center}
      .btn.blue{background:#4f46e5;font-weight:600}
      .webapp{background:linear-gradient(135deg,#4f46e5,#7c3aed);font-weight:700}
      .code{font-family:monospace;background:#0e1621;padding:2px 6px;border-radius:5px}
      .stamp{color:#6c7883;font-size:11px;text-align:center;margin:10px 0}
    </style></head><body><div class="chat">
      <div class="hdr"><div class="ava">🛍️</div><div class="nm"><b>Telegram Shop</b><span>бот · работает</span></div></div>
      <div class="stamp">— сегодня —</div>
      <div class="msg user">/start</div>
      <div class="msg bot">👋 Привет, Анна!<br><br>Это <b>Telegram Shop</b> — каталог товаров с доставкой.<br>Откройте витрину или сайт, добавьте товары в корзину и оплатите удобным способом 👇</div>
      <div class="kb"><div class="btn webapp">🛍 Открыть магазин (Mini App)</div><div class="btn">🌐 Сайт магазина</div><div class="btn">📦 Мои заказы</div><div class="btn">❓ Частые вопросы</div><div class="btn">🏪 Стать продавцом</div></div>
      <div class="msg user">📦 Мои заказы</div>
      <div class="msg bot">📦 <b>Ваши заказы:</b><br><br><b>ORD-1009</b> — ✅ оплачен<br>19.08.2026 • 2 990 ₽ • 🅿️ 5POST — постамат/ПВЗ X5<br><br><b>ORD-1008</b> — 🚚 отправлен<br>18.08.2026 • 3 846 ₽ • 🚚 Курьер по городу<br>Трек: <span class="code">5P-987654321</span></div>
      <div class="stamp">— оплата заказа —</div>
      <div class="msg bot">✅ Спасибо! Ваш заказ <b>ORD-1009</b> оплачен.<br>Мы начали его собирать и скоро свяжемся с вами.<br>💎 Начислено бонусов: 150 ₽</div>
      <div class="stamp">— ежедневная сводка (для админа) —</div>
      <div class="msg bot">📊 <b>Ежедневная сводка · 19.08.2026</b><br><br>Заказов сегодня: 4<br>Выручка сегодня: 12 400 ₽<br><br>Всего заказов: 15<br>Выручка за всё время: 68 300 ₽<br>Пользователей: 120</div>
      <div class="kb"><div class="btn blue">🛍 Открыть магазин (Mini App)</div><div class="btn">🏪 Стать продавцом</div></div>
    </div></body></html>"""
    b.set_content(html)
    time.sleep(0.6)
    shot(b, "t07-bot-chat.png")
    ctx.close()

    # ============ АДМИНКА ============
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/admin/", wait_until="networkidle")
    time.sleep(0.6)
    page.fill("#pass", "admin123")
    page.click('button:has-text("Войти")')
    time.sleep(1.4)
    shot(page, "a01-admin-dashboard.png")
    page.click('button[data-tab="sellers"]')
    time.sleep(0.9)
    shot(page, "a02-admin-sellers.png")
    page.click('button[data-tab="products"]')
    time.sleep(0.9)
    shot(page, "a03-admin-products.png")
    ctx.close()

    browser.close()
    print("DONE")
