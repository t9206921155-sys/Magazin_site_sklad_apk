"""Telegram-магазин: бот (aiogram) + сайт + Mini App + админка (FastAPI) в одном процессе.

Запуск:  python bot.py
Режимы: BOT_MODE=polling (по умолчанию) или BOT_MODE=webhook (нужен WEBAPP_URL).

Автоматика: учёт пользователей, напоминания о брошенной корзине,
ежедневная сводка админу, рассылки, FAQ, связь с менеджером.
"""
import asyncio
import logging
import os
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

import uvicorn
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    MenuButtonWebApp, Message, PreCheckoutQuery, WebAppInfo,
)
from fastapi import Request
from fastapi.responses import Response

import config
import autopost
import mailer
import push
from api import create_app
from delivery_dispatch import after_payment
from payments import get_payment_providers
from store import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("shop")

bot = Bot(token=config.BOT_TOKEN) if config.BOT_TOKEN else None
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

WEBAPP = config.WEBAPP_URL or "https://example.com"

STATUS_LABELS = {
    "pending_payment": "⏳ ожидает оплаты",
    "paid": "✅ оплачен",
    "processing": "🔧 в обработке",
    "shipped": "🚚 отправлен",
    "delivered": "🎉 доставлен",
    "cancelled": "❌ отменён",
}
NEXT_STATUS = {"paid": "processing", "processing": "shipped", "shipped": "delivered"}


def fmt_price(p) -> str:
    return f"{p:,.0f}".replace(",", " ") + " ₽"


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


# ---------------------------------------------------------------- уведомления
async def notify_admins(text: str):
    if not bot or not config.ADMIN_IDS:
        return
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            log.warning("не удалось уведомить админа %s: %s", admin_id, e)


async def notify_new_order(order: dict):
    lines = "\n".join(f"  • {i['name']} × {i['qty']} — {fmt_price(i['price'] * i['qty'])}" for i in order["items"])
    promo = f"\n🎟 Промокод: {order['promo']['code']} (−{fmt_price(order['discount'])})" if order.get("promo") else ""
    free = " (бесплатно 🎉)" if order["delivery"].get("free") else ""

    # уведомление продавцам маркетплейса о их товарах в заказе
    if bot:
        by_seller = {}
        for i in order.get("items", []):
            if i.get("seller_id"):
                by_seller.setdefault(i["seller_id"], []).append(i)
        for sid, items in by_seller.items():
            seller = store.get_seller(sid)
            if seller and seller.get("email") and mailer.available(store):
                my_lines_mail = "\n".join(f"- {i['name']} x{i['qty']} — ваша выручка {fmt_price(i.get('seller_net', 0))}"
                                           for i in items)
                asyncio.create_task(mailer.send_email(
                    store, seller["email"],
                    f"Новый заказ {order['id']} — {store.settings['shop_name']}",
                    f"Здравствуйте!\n\nНа ваши товары поступил заказ {order['id']}:\n"
                    f"{my_lines_mail}\n\nПокупатель: {order['customer']['name']}, {order['customer']['phone']}\n"
                    f"Доставка: {order['delivery']['label']}\n\n"
                    "Средства поступят на ваш баланс после оплаты заказа."))
            if not seller or not seller.get("tg_user_id"):
                continue
            my_lines = "\n".join(f"  • {i['name']} × {i['qty']} — ваша выручка {fmt_price(i.get('seller_net', 0))}"
                                  for i in items)
            try:
                await bot.send_message(
                    seller["tg_user_id"],
                    f"🛒 <b>Новый заказ {order['id']}!</b>\n\n{my_lines}\n\n"
                    f"👤 {order['customer']['name']} • {order['customer']['phone']}\n"
                    f"🚚 {order['delivery']['label']}\n\n"
                    "Деньги поступят на баланс после оплаты заказа.")
            except Exception:
                pass

    await notify_admins(
        f"🆕 <b>Новый заказ {order['id']}</b>\n\n{lines}\n\n"
        f"Доставка: {order['delivery']['label']} ({fmt_price(order['delivery_price'])}){free}\n"
        f"Оплата: {order['payment_method']}{promo}\n"
        f"<b>Итого: {fmt_price(order['total'])}</b>\n\n"
        f"👤 {order['customer']['name']}\n📞 {order['customer']['phone']}\n"
        f"🏠 {order['customer']['address'] or '—'}\n💬 {order['customer']['comment'] or '—'}")

    # push-уведомления приложению «Склад» (работают на HTTPS)
    try:
        await asyncio.to_thread(push.send_push, store, [], "🛒 Новый заказ",
                                f"{order['id']} · {fmt_price(order['total'])} · {order['customer']['name']}")
    except Exception as e:
        log.warning("push new order: %s", e)


async def notify_order_paid(order: dict):
    await notify_admins(
        f"✅ <b>Заказ {order['id']} оплачен!</b> Сумма: {fmt_price(order['total'])}\n"
        f"👤 {order['customer']['name']}, {order['customer']['phone']}")
    # push приложению «Склад»
    try:
        await asyncio.to_thread(push.send_push, store, [], "💰 Заказ оплачен",
                                f"{order['id']} · {fmt_price(order['total'])}")
    except Exception as e:
        log.warning("push paid: %s", e)
    if bot and order.get("tg_user_id"):
        try:
            text = (f"✅ Спасибо! Ваш заказ <b>{order['id']}</b> оплачен.\n"
                    "Мы начали его собирать и скоро свяжемся с вами.")
            if order.get("bonus_amount"):
                text += f"\n💎 Начислено бонусов: {order['bonus_amount']} ₽"
            await bot.send_message(order["tg_user_id"], text)
        except Exception:
            pass

    # уведомления продавцам маркетплейса: продажа оплачена, деньги на балансе
    for it in order.get("items", []):
        if not it.get("seller_id"):
            continue
        seller = store.get_seller(int(it["seller_id"]))
        if not seller:
            continue
        if bot and seller.get("tg_user_id"):
            try:
                await bot.send_message(
                    seller["tg_user_id"],
                    f"💰 <b>Оплачен заказ {order['id']}!</b>\n\n"
                    f"{it['name']} × {it['qty']} — ваша выручка {fmt_price(it.get('seller_net', 0))}\n\n"
                    "Средства зачислены на баланс кабинета продавца. 🎉")
            except Exception:
                pass
        if seller.get("email") and mailer.available(store):
            asyncio.create_task(mailer.send_email(
                store, seller["email"],
                f"Продажа оплачена: заказ {order['id']} — {store.settings['shop_name']}",
                f"Здравствуйте!\n\nОплачен заказ {order['id']}:\n"
                f"{it['name']} x{it['qty']} — ваша выручка {fmt_price(it.get('seller_net', 0))}\n\n"
                "Средства зачислены на ваш баланс. Спасибо за продажи!"))


async def notify_customer_status(order: dict):
    if bot and order.get("tg_user_id"):
        try:
            text = f"📦 Заказ <b>{order['id']}</b>: {STATUS_LABELS.get(order['status'], order['status'])}."
            if order.get("delivery", {}).get("tracking"):
                text += f"\nТрек: <code>{order['delivery']['tracking']}</code>"
            await bot.send_message(order["tg_user_id"], text)
        except Exception:
            pass


# ---------------------------------------------------------------- учёт пользователей
@router.message(F.from_user)
async def track_user(message: Message):
    u = message.from_user
    store.upsert_user(u.id, u.username, u.first_name, u.last_name)


# ------------------------------------------------------------------ /start
@router.message(Command("start"))
async def cmd_start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Открыть магазин (Mini App)", web_app=WebAppInfo(url=WEBAPP))],
        [InlineKeyboardButton(text="🌐 Сайт магазина", url=config.WEBAPP_URL or "https://example.com")],
        [InlineKeyboardButton(text="📦 Мои заказы", callback_data="my_orders")],
        [InlineKeyboardButton(text="❓ Частые вопросы", callback_data="faq")],
        [InlineKeyboardButton(text="🏪 Стать продавцом", url=(config.WEBAPP_URL or "http://localhost:8000") + "/become-seller")],
    ])
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"Это <b>{store.settings['shop_name']}</b> — каталог товаров с доставкой.\n"
        "Откройте витрину или сайт, добавьте товары в корзину и оплатите удобным способом 👇",
        reply_markup=kb)


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🛍 <b>Как покупать:</b> откройте магазин, добавьте товары в корзину, оформите заказ и оплатите.\n"
        "💳 Оплата: карта (ЮKassa, Т-Банк), СБП, криптовалюта, Telegram Stars.\n"
        "🚚 Доставка: самовывоз, курьер, почта, СДЭК, 5POST, Яндекс Доставка.\n"
        "🎟 Промокод вводится при оформлении заказа.\n"
        "📦 Команды: /start, /orders, /faq, /support.")


@router.message(Command("orders"))
async def cmd_orders(message: Message):
    orders = store.orders_for_user(tg_user_id=message.from_user.id)
    if not orders:
        await message.answer("У вас пока нет заказов 😔")
        return
    parts = [f"<b>{o['id']}</b> — {STATUS_LABELS.get(o['status'], o['status'])}\n"
             f"{o['created_at'][:10]} • {fmt_price(o['total'])} • {o['delivery']['label']}"
             for o in orders[:10]]
    await message.answer("📦 <b>Ваши заказы:</b>\n\n" + "\n\n".join(parts))


@router.callback_query(F.data == "my_orders")
async def cb_my_orders(cb: CallbackQuery):
    await cb.message.delete()
    await cmd_orders(cb.message)
    await cb.answer()


@router.message(Command("bonus"))
async def cmd_bonus(message: Message):
    balance = store.bonus_balance(f"tg:{message.from_user.id}")
    loy = store.settings.get("loyalty") or {}
    if not loy.get("enabled"):
        await message.answer("💎 Бонусная программа пока не запущена. Заходите позже!")
        return
    await message.answer(
        f"💎 <b>Ваши бонусы</b>\n\nБаланс: <b>{fmt_price(balance)}</b>\n\n"
        f"За каждый оплаченный заказ начисляется {int(loy.get('rate_percent') or 0)}% "
        "от суммы. Баллами можно оплатить часть следующего заказа при оформлении — "
        "просто отметьте «Списать бонусы» в корзине.")



class SellerReg(StatesGroup):
    store_name = State()
    phone = State()


@router.message(Command("seller"))
async def cmd_seller(message: Message, state: FSMContext):
    mp = store.settings.get("marketplace") or {}
    if not mp.get("enabled"):
        await message.answer("🏪 Регистрация продавцов временно закрыта.")
        return
    existing = store.get_seller(tg_user_id=message.from_user.id)
    if existing:
        await message.answer(
            f"🏪 Ваша витрина: <b>{existing['store_name']}</b>\n"
            f"Статус: {existing['status']}\n"
            f"Ссылка: {config.WEBAPP_URL or 'http://localhost:8000'}/seller/{existing['slug']}\n"
            f"Кабинет продавца: {config.WEBAPP_URL or 'http://localhost:8000'}/seller\n\n"
            f"🔑 Ключ доступа: <code>{existing['key']}</code>")
        return
    await state.set_state(SellerReg.store_name)
    await message.answer("🏪 <b>Открытие витрины</b>\n\nШаг 1/2. Как будет называться ваш магазин?")


@router.message(SellerReg.store_name)
async def seller_step_name(message: Message, state: FSMContext):
    await state.update_data(store_name=message.text.strip())
    await state.set_state(SellerReg.phone)
    await message.answer("Шаг 2/2. 📞 Ваш телефон для связи:")


@router.message(SellerReg.phone)
async def seller_step_phone(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    try:
        seller = store.register_seller({
            "store_name": data["store_name"], "phone": message.text.strip(),
            "tg_user_id": message.from_user.id,
        })
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return
    await notify_admins(f"🏪 <b>Новый продавец:</b> {seller['store_name']}\n📞 {seller['phone']}")
    await message.answer(
        f"✅ Витрина <b>{seller['store_name']}</b> создана!\n\n"
        f"Статус: {'🟢 активна' if seller['status'] == 'active' else '⏳ ждёт подтверждения администратора'}\n"
        f"🌐 Витрина: {config.WEBAPP_URL or 'http://localhost:8000'}/seller/{seller['slug']}\n"
        f"⚙️ Кабинет: {config.WEBAPP_URL or 'http://localhost:8000'}/seller\n\n"
        f"🔑 <b>Ключ доступа (сохраните!):</b>\n<code>{seller['key']}</code>\n\n"
        "В кабинете добавляйте товары, создавайте промокоды и следите за балансом.")

@router.message(Command("stock"))
async def cmd_stock(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Команда доступна только администратору.")
        return
    products = [p for p in store.products() if not p.get("is_archived")]
    total_qty = sum(p["stock"] for p in products if p.get("stock", -1) >= 0)
    value = sum(p["price"] * p["stock"] for p in products if p.get("stock", -1) >= 0)
    await message.answer(
        f"📦 <b>Остатки склада</b>\n\n"
        f"Позиций: {len(products)}\n"
        f"Единиц товара: {total_qty}\n"
        f"Оценочная стоимость: {fmt_price(value)}")


@router.message(Command("low_stock"))
async def cmd_low_stock(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Команда доступна только администратору.")
        return
    low = [p for p in store.products()
           if not p.get("is_archived") and 0 <= p.get("stock", -1) < 5]
    if not low:
        await message.answer("✅ Товаров с низким остатком нет.")
        return
    lines = "\n".join(f"• {p['name'][:40]} — остаток <b>{p['stock']}</b> шт." for p in low[:15])
    await message.answer(f"⚠️ <b>Низкие остатки ({len(low)}):</b>\n\n{lines}")


@router.message(Command("publish"))
async def cmd_publish(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Команда доступна только администратору.")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /publish <артикул или id товара>\n"
                             "Публикует товар в настроенные каналы (Telegram/VK/Instagram/Avito).")
        return
    q = parts[1].strip()
    product = None
    try:
        product = store.get_product(int(q))
    except ValueError:
        product = next((p for p in store.products() if str(p.get("code") or "") == q), None)
    if not product:
        await message.answer("❌ Товар не найден.")
        return
    res = await autopost.post_product(store, product, bot, force=True)
    ok = [k for k, v in res.items() if isinstance(v, dict) and v.get("ok")]
    await message.answer(
        f"📣 Товар «{product['name']}» отправлен.\n"
        f"Успешно: {', '.join(ok) or 'нет каналов (проверьте настройки автопостинга)'}")


# ---------------------------------------------------------------- поддержка и FAQ
@router.message(Command("support"))
async def cmd_support(message: Message):
    m = store.settings.get("manager") or {}
    username = (m.get("username") or "").strip().lstrip("@")
    text = (m.get("text") or "Мы на связи! Напишите нам — ответим в течение дня.").strip()
    kb = None
    if username:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать менеджеру", url=f"https://t.me/{username}")]])
    await message.answer(f"🙋 <b>Связь с нами</b>\n\n{text}", reply_markup=kb)


def faq_kb() -> InlineKeyboardMarkup:
    faq = store.settings.get("faq") or []
    buttons = [[InlineKeyboardButton(text=q["q"][:60], callback_data=f"faq:{i}")] for i, q in enumerate(faq)]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("faq"))
async def cmd_faq(message: Message):
    faq = store.settings.get("faq") or []
    if not faq:
        await message.answer("Раздел вопросов пока пуст.")
        return
    await message.answer("❓ <b>Частые вопросы</b> — выберите вопрос:", reply_markup=faq_kb())


@router.callback_query(F.data == "faq")
async def cb_faq(cb: CallbackQuery):
    await cb.message.delete()
    await cmd_faq(cb.message)
    await cb.answer()


@router.callback_query(F.data.startswith("faq:"))
async def cb_faq_answer(cb: CallbackQuery):
    idx = int(cb.data.split(":", 1)[1])
    faq = store.settings.get("faq") or []
    if idx >= len(faq):
        await cb.answer()
        return
    q, a = faq[idx]["q"], faq[idx]["a"]
    await cb.message.answer(f"<b>{q}</b>\n\n{a}", reply_markup=faq_kb())
    await cb.answer()


# ------------------------------------------------- Telegram Stars (XTR)
@router.pre_checkout_query()
async def on_pre_checkout(pcq: PreCheckoutQuery):
    await pcq.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    order = store.confirm_payment(payload, "stars", message.successful_payment.telegram_payment_charge_id)
    if order:
        store.set_payment_method(order["id"], "stars")
        await notify_order_paid(order)
        await message.answer(
            f"✅ Оплата заказа <b>{order['id']}</b> прошла успешно!\n"
            "Мы начали его собирать и скоро свяжемся с вами.")
        asyncio.create_task(after_payment(store, order["id"], notify_admins))
    else:
        await message.answer("✅ Платёж получен. Спасибо!")


# ---------------------------------------------------------------- рассылки
async def do_broadcast(text: str) -> dict:
    """Рассылка сообщения всем пользователям бота. Возвращает статистику."""
    if not bot:
        return {"error": "Бот не запущен (нет BOT_TOKEN)"}
    users = store.all_users()
    ok = fail = 0
    for u in users:
        try:
            await bot.send_message(u["tg_user_id"], text)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)  # ~20 сообщений/сек, лимит Telegram — 30
    log.info("Рассылка завершена: %d отправлено, %d ошибок", ok, fail)
    return {"sent": ok, "failed": fail, "total": len(users)}


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Команда доступна только администратору.")
        return
    text = message.text.split(maxsplit=1)
    if len(text) < 2:
        await message.answer("Использование: /broadcast <текст рассылки>\n"
                             f"Получателей: {store.users_count()}")
        return
    result = await do_broadcast(text[1])
    await message.answer(f"📣 Рассылка завершена: отправлено {result['sent']}, ошибок {result['failed']}")


# ---------------------------------------------------------------- отчёты админу
@router.message(Command("report"))
async def cmd_report(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Команда доступна только администратору.")
        return
    s = store.stats()
    t = store.today_stats()
    top = store.top_products(3)
    lines = [f"• {p['name'][:40]} — {p['qty']} шт." for p in top] or ["—"]
    await message.answer(
        f"📊 <b>Сводка · {store.settings['shop_name']}</b>\n\n"
        f"Сегодня: заказов {t['orders']}, выручка {fmt_price(t['revenue'])}\n"
        f"Всего: заказов {s['orders']}, выручка {fmt_price(s['revenue'])}\n"
        f"Товаров: {s['products']} • Пользователей: {s['users']}\n\n"
        f"<b>Топ продаж:</b>\n" + "\n".join(lines))


# ------------------------------------------------------- админ-панель (бот)
class AddProduct(StatesGroup):
    name = State()
    price = State()
    description = State()
    category = State()
    category_custom = State()
    photo = State()


def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="adm_add")],
        [InlineKeyboardButton(text="🗑 Удалить товар", callback_data="adm_del")],
        [InlineKeyboardButton(text="📦 Заказы", callback_data="adm_orders")],
    ])


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Команда доступна только администратору.")
        return
    await message.answer(
        f"🛠 <b>Админ-панель · {store.settings['shop_name']}</b>\n\n"
        f"Товаров: {len(store.products())} • Активных заказов: {store.stats()['active']}\n\n"
        "Полная веб-админка (товары, промокоды, рассылки, отчёты, настройки, 1С): /admin на сайте",
        reply_markup=admin_panel_kb())


@router.callback_query(F.data == "adm_panel")
async def cb_adm_panel(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ Нет доступа", show_alert=True)
        return
    await cb.message.edit_text(
        f"🛠 <b>Админ-панель · {store.settings['shop_name']}</b>\n\n"
        f"Товаров: {len(store.products())} • Активных заказов: {store.stats()['active']}",
        reply_markup=admin_panel_kb())
    await cb.answer()


@router.callback_query(F.data == "adm_add")
async def cb_add(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ Нет доступа", show_alert=True)
        return
    await state.set_state(AddProduct.name)
    await cb.message.answer("➕ <b>Новый товар</b>\n\nШаг 1/5. Введите название товара:")
    await cb.answer()


@router.message(AddProduct.name)
async def step_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddProduct.price)
    await message.answer("Шаг 2/5. 💰 Введите цену в рублях (число), например: <code>1990</code>")


@router.message(AddProduct.price)
async def step_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", ".").replace(" ", ""))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите корректную цену (число):")
        return
    await state.update_data(price=int(price))
    await state.set_state(AddProduct.description)
    await message.answer("Шаг 3/5. 📝 Описание товара (или «—», чтобы пропустить):")


@router.message(AddProduct.description)
async def step_desc(message: Message, state: FSMContext):
    desc = message.text.strip()
    await state.update_data(description="" if desc == "—" else desc)
    await state.set_state(AddProduct.category)
    cats = store.categories()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c, callback_data=f"cat:{c}")] for c in cats
    ] + [[InlineKeyboardButton(text="➕ Новая категория", callback_data="cat:NEW")]])
    await message.answer("Шаг 4/5. 🏷 Выберите категорию:", reply_markup=kb)


@router.callback_query(AddProduct.category, F.data.startswith("cat:"))
async def step_cat(cb: CallbackQuery, state: FSMContext):
    cat = cb.data.split(":", 1)[1]
    if cat == "NEW":
        await state.set_state(AddProduct.category_custom)
        await cb.message.answer("Введите название новой категории:")
        await cb.answer()
        return
    await state.update_data(category=cat)
    await state.set_state(AddProduct.photo)
    await cb.message.answer("Шаг 5/5. 🖼 Отправьте фото товара (картинкой) или URL изображения:")
    await cb.answer()


@router.message(AddProduct.category_custom)
async def step_cat_custom(message: Message, state: FSMContext):
    await state.update_data(category=message.text.strip())
    await state.set_state(AddProduct.photo)
    await message.answer("Шаг 5/5. 🖼 Отправьте фото товара (картинкой) или URL изображения:")


@router.message(AddProduct.photo)
async def step_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photo = None
    if message.photo:
        pid = store.next_product_id()
        rel = f"/webapp/img/products/up_{pid}.jpg"
        dest = os.path.join(config.WEBAPP_DIR, "img", "products", f"up_{pid}.jpg")
        try:
            photo_file = await bot.get_file(message.photo[-1].file_id)
            await bot.download(photo_file, destination=dest)
            photo = rel
        except Exception as e:
            log.warning("не удалось скачать фото: %s", e)
            await message.answer("Не удалось сохранить фото, попробуйте ещё раз:")
            return
    elif message.text and message.text.strip().startswith("http"):
        photo = message.text.strip()
    else:
        await message.answer("Отправьте фото картинкой или ссылку на изображение (http...):")
        return
    product = store.add_product({**data, "photo": photo})
    await state.clear()
    await message.answer(f"✅ Товар добавлен:\n<b>{product['name']}</b> — {fmt_price(product['price'])}\n"
                         f"Категория: {product['category']} • ID: {product['id']}")
    asyncio.create_task(autopost.post_product(store, product, bot))


@router.callback_query(F.data == "adm_del")
async def cb_del(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ Нет доступа", show_alert=True)
        return
    products = store.products()
    if not products:
        await cb.answer("Каталог пуст", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🗑 {p['name'][:38]} — {fmt_price(p['price'])}", callback_data=f"del:{p['id']}")]
        for p in products[:20]
    ] + [[InlineKeyboardButton(text="« Назад", callback_data="adm_panel")]])
    await cb.message.edit_text("Выберите товар для удаления:", reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("del:"))
async def cb_del_confirm(cb: CallbackQuery):
    pid = int(cb.data.split(":")[1])
    p = store.get_product(pid)
    if not p:
        await cb.answer("Товар не найден", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delok:{pid}")],
        [InlineKeyboardButton(text="« Назад", callback_data="adm_del")],
    ])
    await cb.message.edit_text(f"Удалить товар <b>{p['name']}</b> ({fmt_price(p['price'])})?", reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("delok:"))
async def cb_del_ok(cb: CallbackQuery):
    pid = int(cb.data.split(":")[1])
    store.delete_product(pid)
    await cb.message.edit_text("🗑 Товар удалён из каталога.")
    await cb.answer()


# --- заказы и статусы ---
def order_detail_text(o: dict) -> str:
    lines = "\n".join(f"• {i['name']} × {i['qty']} — {fmt_price(i['price'] * i['qty'])}" for i in o["items"])
    promo = f"\n🎟 {o['promo']['code']} — скидка {fmt_price(o['discount'])}" if o.get("promo") else ""
    tracking = f"\n🚚 Трек: <code>{o['delivery']['tracking']}</code>" if o.get("delivery", {}).get("tracking") else ""
    return (f"📦 <b>{o['id']}</b> — {STATUS_LABELS.get(o['status'], o['status'])}\n\n{lines}\n\n"
            f"Доставка: {o['delivery']['label']} (+{fmt_price(o['delivery_price'])}){tracking}\n"
            f"Оплата: {o.get('payment_method', '—')}{promo}\n<b>Итого: {fmt_price(o['total'])}</b>\n\n"
            f"👤 {o['customer']['name']}\n📞 {o['customer']['phone']}\n🏠 {o['customer']['address'] or '—'}\n"
            f"💬 {o['customer']['comment'] or '—'}\n\n🕐 {o['created_at'][:16].replace('T', ' ')}")


def order_detail_kb(oid: str, status: str, payment=None) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="« К списку", callback_data="adm_orders")]]
    if payment and payment.get("provider") == "transfer" \
            and payment.get("status") in ("pending", "verifying") and status == "pending_payment":
        buttons.insert(0, [InlineKeyboardButton(text="✅ Подтвердить перевод", callback_data=f"conf:{oid}")])
    if status in NEXT_STATUS:
        buttons.insert(0, [InlineKeyboardButton(
            text=f"→ {STATUS_LABELS[NEXT_STATUS[status]]}", callback_data=f"st:{oid}:{NEXT_STATUS[status]}")])
    if status not in ("cancelled", "delivered"):
        buttons.insert(0, [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"st:{oid}:cancelled")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "adm_orders")
async def cb_orders(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ Нет доступа", show_alert=True)
        return
    orders = store.orders(limit=10)
    if not orders:
        await cb.answer("Заказов пока нет", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{o['id']} • {STATUS_LABELS.get(o['status'], o['status'])} • {fmt_price(o['total'])}",
            callback_data=f"ord:{o['id']}")] for o in orders
    ] + [[InlineKeyboardButton(text="« Назад", callback_data="adm_panel")]])
    await cb.message.edit_text("📦 Последние заказы:", reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("ord:"))
async def cb_order_detail(cb: CallbackQuery):
    oid = cb.data.split(":", 1)[1]
    o = store.get_order(oid)
    if not o:
        await cb.answer("Заказ не найден", show_alert=True)
        return
    await cb.message.edit_text(order_detail_text(o),
                               reply_markup=order_detail_kb(oid, o["status"], o.get("payment")))
    await cb.answer()


@router.callback_query(F.data.startswith("conf:"))
async def cb_confirm_transfer(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ Нет доступа", show_alert=True)
        return
    oid = cb.data.split(":", 1)[1]
    o = store.get_order(oid)
    if not o:
        await cb.answer("Заказ не найден", show_alert=True)
        return
    o = store.confirm_payment(oid, "transfer", "manual")
    store.set_payment_method(oid, "transfer")
    await notify_order_paid(o)
    asyncio.create_task(after_payment(store, oid, notify_admins))
    await cb.message.edit_text(order_detail_text(o),
                               reply_markup=order_detail_kb(oid, o["status"], o.get("payment")))
    await cb.answer("Оплата подтверждена ✅")


@router.callback_query(F.data.startswith("st:"))
async def cb_status(cb: CallbackQuery):
    _, oid, status = cb.data.split(":", 2)
    o = store.set_order_status(oid, status)
    if not o:
        await cb.answer("Заказ не найден", show_alert=True)
        return
    await notify_customer_status(o)
    await cb.message.edit_text(order_detail_text(o),
                               reply_markup=order_detail_kb(oid, o["status"], o.get("payment")))
    await cb.answer(f"Статус: {STATUS_LABELS.get(status, status)}")


# ------------------------------------------------------------ фоновая автоматика
async def abandoned_cart_loop():
    """Напоминания о неоплаченных заказах (брошенная корзина)."""
    while True:
        try:
            minutes = int(store.settings.get("abandoned_cart_minutes") or 0)
            if bot and minutes > 0:
                for o in store.pending_abandoned(minutes):
                    link = config.WEBAPP_URL or f"http://localhost:{config.PORT}/"
                    try:
                        await bot.send_message(
                            o["tg_user_id"],
                            f"🛒 Вы оформили заказ <b>{o['id']}</b> на {fmt_price(o['total'])}, "
                            f"но не завершили оплату.\n\nПерейдите в магазин, чтобы продолжить: {link}",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="🛍 Открыть магазин", web_app=WebAppInfo(url=WEBAPP))]]))
                        store.set_reminded(o["id"])
                        log.info("Напоминание о заказе %s отправлено", o["id"])
                    except Exception as e:
                        log.warning("Напоминание %s: %s", o["id"], e)
        except Exception as e:
            log.warning("abandoned_cart_loop: %s", e)
        await asyncio.sleep(300)


async def daily_report_loop():
    """Ежедневная сводка админу в Telegram (в заданный час)."""
    sent_date = None
    while True:
        try:
            # авторазморозка холда продавцов (эскроу) — работает независимо от бота
            released = store.auto_release_held()
            if released:
                log.info("auto_release_held: разморожено заказов: %s", released)
            if bot and store.settings.get("daily_report") and config.ADMIN_IDS:
                tz_name = store.settings.get("timezone") or "Europe/Moscow"
                hour = int(store.settings.get("daily_report_hour") or 9)
                try:
                    tz = ZoneInfo(tz_name)
                except Exception:
                    tz = ZoneInfo("Europe/Moscow")
                now = datetime.now(tz)
                if now.hour >= hour and sent_date != now.date():
                    s = store.stats()
                    t = store.today_stats()
                    await notify_admins(
                        f"📊 <b>Ежедневная сводка · {now:%d.%m.%Y}</b>\n\n"
                        f"Заказов сегодня: {t['orders']}\n"
                        f"Выручка сегодня: {fmt_price(t['revenue'])}\n\n"
                        f"Всего заказов: {s['orders']}\n"
                        f"Выручка за всё время: {fmt_price(s['revenue'])}\n"
                        f"Пользователей: {s['users']}")
                    sent_date = now.date()
        except Exception as e:
            log.warning("daily_report_loop: %s", e)
        await asyncio.sleep(1800)


async def scheduled_posts_loop():
    """Отложенные публикации в соцсети: проверка каждые 30 секунд."""
    while True:
        try:
            for post in store.due_scheduled_posts():
                product = store.get_product(int(post["product_id"]))
                if not product:
                    store.set_post_status(post["id"], "failed", "Товар удалён")
                    continue
                res = await autopost.post_product(store, product, bot, force=True,
                                                  platform=post["platform"])
                target = res.get(post["platform"]) if isinstance(res.get(post["platform"]), dict) else None
                if target and target.get("ok"):
                    store.set_post_status(post["id"], "published")
                    log.info("Публикация %s выполнена: %s", post["id"], post["platform"])
                else:
                    store.set_post_status(post["id"], "failed",
                                          str((target or {}).get("error", "нет канала"))[:300])
        except Exception as e:
            log.warning("scheduled_posts_loop: %s", e)
        await asyncio.sleep(30)


# ------------------------------------------------------------ запуск сервера
async def setup_menu_button():
    if bot and config.WEBAPP_URL:
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="🛍 Каталог", web_app=WebAppInfo(url=config.WEBAPP_URL)))
        except Exception as e:
            log.warning("Не удалось настроить кнопку меню: %s", e)


async def main():
    app = None
    if bot:
        if config.BOT_MODE == "webhook" and config.WEBAPP_URL:
            secret = config.WEBHOOK_SECRET or secrets.token_hex(24)
            await bot.delete_webhook(drop_pending_updates=True)
            await bot.set_webhook(url=config.WEBAPP_URL + config.WEBHOOK_PATH,
                                  secret_token=secret,
                                  drop_pending_updates=True)
            log.info("Бот работает в режиме webhook: %s%s", config.WEBAPP_URL, config.WEBHOOK_PATH)
        else:
            await bot.delete_webhook(drop_pending_updates=True)
            asyncio.create_task(dp.start_polling(bot, handle_signals=False))
            log.info("Бот запущен (polling)")
        await setup_menu_button()
        asyncio.create_task(abandoned_cart_loop())
        asyncio.create_task(daily_report_loop())
    else:
        log.warning("BOT_TOKEN не задан — бот отключён. Работают сайт /, витрина /app и админка /admin.")
    asyncio.create_task(scheduled_posts_loop())

    providers = get_payment_providers(bot)
    app = create_app(store, providers, bot, notify_new_order, notify_order_paid, notify_customer_status,
                     notify_admins, broadcast_sender=do_broadcast)

    # вебхук Telegram
    if bot and config.BOT_MODE == "webhook" and config.WEBAPP_URL and app is not None:
        secret = config.WEBHOOK_SECRET or secrets.token_hex(24)

        @app.post(config.WEBHOOK_PATH)
        async def tg_webhook(request: Request):
            if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
                return Response(status_code=403, content="forbidden")
            try:
                update = types.Update.model_validate(await request.json())
                await dp.feed_update(bot, update)
            except Exception as e:
                log.warning("webhook: %s", e)
            return {"ok": True}

    server_config = uvicorn.Config(app, host=config.HOST, port=config.PORT, log_level="warning")
    server = uvicorn.Server(server_config)
    log.info("Сайт: http://%s:%s/ | Mini App: /app | Админка: /admin", config.HOST, config.PORT)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
