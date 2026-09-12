#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор PDF-руководства «Telegram Shop — установка и настройка».

Запуск из корня репо:  python3 telegram-shop/scripts/make_user_manual.py
Результат:             docs/Telegram-Shop-руководство.pdf
"""
import datetime
import os
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle, PageBreak, KeepTogether,
                                HRFlowable)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "docs", "Telegram-Shop-руководство.pdf")

FONTS = "/usr/share/fonts/truetype/dejavu"
pdfmetrics.registerFont(TTFont("DV", f"{FONTS}/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVB", f"{FONTS}/DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DVM", f"{FONTS}/DejaVuSansMono.ttf"))
pdfmetrics.registerFont(TTFont("DVMB", f"{FONTS}/DejaVuSansMono-Bold.ttf"))

TEAL = colors.HexColor("#0F766E")
DARK = colors.HexColor("#0F172A")
SLATE = colors.HexColor("#475569")
LIGHT = colors.HexColor("#F1F5F9")
AMBER = colors.HexColor("#FEF3C7")
AMBER_B = colors.HexColor("#B45309")
GREEN = colors.HexColor("#ECFDF5")
GREEN_B = colors.HexColor("#047857")
BLUE = colors.HexColor("#EFF6FF")
BLUE_B = colors.HexColor("#1D4ED8")
GRID = colors.HexColor("#CBD5E1")

S = {
    "h1": ParagraphStyle("h1", fontName="DVB", fontSize=16, leading=20, textColor=TEAL, spaceBefore=14, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName="DVB", fontSize=12, leading=15, textColor=DARK, spaceBefore=10, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="DV", fontSize=9.5, leading=13.5, textColor=DARK, spaceAfter=4),
    "li": ParagraphStyle("li", fontName="DV", fontSize=9.5, leading=13.5, textColor=DARK, leftIndent=10, bulletIndent=2, spaceAfter=2),
    "cell": ParagraphStyle("cell", fontName="DV", fontSize=8.5, leading=11, textColor=DARK),
    "cellb": ParagraphStyle("cellb", fontName="DVB", fontSize=8.5, leading=11, textColor=colors.white),
    "code": ParagraphStyle("code", fontName="DVM", fontSize=8, leading=10.5, textColor=DARK),
    "note": ParagraphStyle("note", fontName="DV", fontSize=9, leading=12.5, textColor=DARK),
    "toc": ParagraphStyle("toc", fontName="DV", fontSize=10.5, leading=17, textColor=DARK),
}


def h1(num, text):
    return [Paragraph(f"{num}. {text}", S["h1"]),
            HRFlowable(width="100%", thickness=1.2, color=TEAL, spaceAfter=6)]


def p(text):
    return Paragraph(text, S["body"])


def li(items):
    return [Paragraph(f"• {t}", S["li"]) for t in items]


def code(text, title=None):
    rows = [[Paragraph(title, S["cellb"])]] if title else []
    rows.append([Paragraph(text.replace("\n", "<br/>").replace(" ", "&nbsp;"), S["code"])])
    t = Table(rows, colWidths=[168 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, -1), (0, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.6, GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ] + ([("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#E2E8F0"))] if title else [])))
    return [Spacer(1, 2), t, Spacer(1, 4)]


def box(kind, text):
    conf = {"ВАЖНО": (AMBER, AMBER_B), "ПРИМЕР": (GREEN, GREEN_B), "СОВЕТ": (BLUE, BLUE_B)}
    bg, border = conf[kind]
    t = Table([[Paragraph(f"<font name='DVB' color='#{border.hexval()[2:]}'><super>▲</super> {kind}</font><br/>" + text, S["note"])]],
              colWidths=[168 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 2.4, border),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [Spacer(1, 2), t, Spacer(1, 4)]


def table(header, rows, widths):
    data = [[Paragraph(x, S["cellb"]) for x in header]]
    for r in rows:
        data.append([Paragraph(c, S["cell"]) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return [Spacer(1, 2), t, Spacer(1, 5)]


def cover():
    e = []
    e.append(Spacer(1, 55 * mm))
    band = Table([[Paragraph("<font name='DVB' size=30 color=white>Telegram Shop</font>", S["cell"])],
                  [Paragraph("<font name='DV' size=13 color=#CCFBF1>Маркетплейс + SEO-сайт + Telegram Mini App<br/>+ Склад PWA + Android APK</font>", S["cell"])]],
                 colWidths=[170 * mm])
    band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL),
                              ("LEFTPADDING", (0, 0), (-1, -1), 14), ("TOPPADDING", (0, 0), (0, 0), 12),
                              ("BOTTOMPADDING", (0, -1), (-1, -1), 14)]))
    e.append(band)
    e.append(Spacer(1, 14 * mm))
    e.append(Paragraph("<font name='DVB' size=17 color='#0F172A'>Руководство по установке и настройке</font>", S["cell"]))
    e.append(Spacer(1, 4))
    e.append(Paragraph("<font name='DV' size=11 color='#475569'>с примерами для каждого компонента системы</font>", S["cell"]))
    e.append(Spacer(1, 60 * mm))
    meta = Table([[Paragraph("<font name='DVB' size=10>Версия документа:</font> <font name='DV' size=10>1.1.0</font>", S["cell"]),
                  Paragraph(f"<font name='DVB' size=10>Дата:</font> <font name='DV' size=10>{datetime.date.today().strftime('%d.%m.%Y')}</font>", S["cell"])],
                 [Paragraph("<font name='DVB' size=10>Состав:</font> <font name='DV' size=10>сайт, бот, Mini App, маркетплейс, склад, APK</font>", S["cell"]),
                  Paragraph("<font name='DVB' size=10>Лицензия:</font> <font name='DV' size=10>внутренний проект</font>", S["cell"])]],
                colWidths=[85 * mm, 85 * mm])
    meta.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, GRID),
                              ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                              ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    e.append(meta)
    return e


TOC = [
    "1. Что это за система", "2. Требования", "3. Установка «из коробки» (4 способа)",
    "4. Файл .env: все переменные с примерами", "5. Telegram-бот и Mini App",
    "6. Склад: вход, роли, мультисклад", "7. Сканеры штрих-кодов (HID, ТСД, камера)",
    "8. Печать этикеток: ZPL/EPL, IP-принтер, Wi-Fi с телефона", "9. Android APK «Склад 1.1.0»",
    "10. Обмен с 1С", "11. Маркетплейс и кабинет продавца", "12. SEO и продвижение",
    "13. Безопасность и HTTPS", "14. Резервные копии", "15. Обновление и пересборка APK",
    "16. Диагностика и FAQ",
]


def toc_page():
    e = [Paragraph("Содержание", S["h1"]), HRFlowable(width="100%", thickness=1.2, color=TEAL, spaceAfter=10)]
    half = (len(TOC) + 1) // 2
    rows = []
    for i in range(half):
        left = TOC[i]
        right = TOC[i + half] if i + half < len(TOC) else ""
        rows.append([Paragraph(left, S["toc"]), Paragraph(right, S["toc"])])
    t = Table(rows, colWidths=[84 * mm, 84 * mm])
    t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    e.append(t)
    e += box("СОВЕТ", "Короткий путь: локально за 5 минут — раздел 3.1; телефон + склад — раздел 9; "
                      "принтер — раздел 8. production на VPS — 3.4 и 13.")
    return e


def build():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=21 * mm, rightMargin=21 * mm,
                          topMargin=18 * mm, bottomMargin=16 * mm,
                          title="Telegram Shop — Руководство по установке и настройке")

    def footer(canv, d):
        canv.saveState()
        canv.setFont("DV", 7.5)
        canv.setFillColor(SLATE)
        canv.drawString(21 * mm, 9 * mm, "Telegram Shop — руководство по установке и настройке")
        canv.drawRightString(189 * mm, 9 * mm, f"стр. {canv.getPageNumber()}")
        canv.setStrokeColor(GRID)
        canv.setLineWidth(0.5)
        canv.line(21 * mm, 12 * mm, 189 * mm, 12 * mm)
        canv.restoreState()

    frame_cover = Frame(21 * mm, 16 * mm, 168 * mm, 263 * mm, id="cover")
    frame = Frame(21 * mm, 16 * mm, 168 * mm, 262 * mm, id="main")
    doc.addPageTemplates([PageTemplate(id="Cover", frames=[frame_cover], onPage=footer),
                          PageTemplate(id="Main", frames=[frame], onPage=footer)])

    story = cover()
    story.append(PageBreak())
    story += toc_page()
    story.append(PageBreak())

    # ---------- 1 ----------
    story += h1(1, "Что это за система")
    story.append(p("<b>Telegram Shop</b> — монолитный Python-проект (FastAPI) «всё в одном»: "
                   "SEO-сайт с каталогом, Telegram-бот с Mini App, маркетплейс продавцов, мобильный склад "
                   "и Android-приложение. Один процесс обслуживает все роли."))
    story += table(
        ["Компонент", "Адрес по умолчанию", "Кто пользуется"],
        [["SEO-сайт и каталог", "<font name='DVM'>/</font>", "покупатели, поисковики"],
         ["Telegram Mini App", "<font name='DVM'>/app</font>", "покупатели в Telegram"],
         ["Маркетплейс / кабинет продавца", "<font name='DVM'>/seller</font>", "продавцы"],
         ["Админка", "<font name='DVM'>/admin</font>", "владелец, админы"],
         ["Склад PWA", "<font name='DVM'>/warehouse/</font>", "сотрудники склада"],
         ["Android APK «Склад»", "<font name='DVM'>/download/android</font>", "сотрудники склада"],
         ["Обмен с 1С", "<font name='DVM'>/1c/*</font>", "1С:Предприятие"],
         ["Страницы SEO", "<font name='DVM'>/sitemap.xml, /robots.txt</font>", "Яндекс, Google"]],
        [58 * mm, 62 * mm, 48 * mm])
    story.append(p("Хранение данных: SQLite (по умолчанию, файл <font name='DVM'>telegram-shop/data/shop.db</font>), "
                   "опционально MySQL/MariaDB или Supabase; фото — локально, S3-совместимое хранилище или Яндекс Диск."))

    # ---------- 2 ----------
    story += h1(2, "Требования")
    story += li(["<b>Сервер:</b> Ubuntu 22.04+/Debian 12, 1 vCPU / 1 ГБ RAM / 10 ГБ SSD (минимум), ",
                 "<b>Python</b> 3.10–3.12 + pip + venv; <b>git</b>",
                 "<b>Для HTTPS:</b> домен, A-запись на сервер, порты 80/443 (nginx + certbot ставит bootstrap)",
                 "<b>Для сборки APK:</b> не нужно на сервере — APK собирается CI GitHub Actions",
                 "<b>Опционально:</b> MySQL/MariaDB, S3-хранилище (Яндекс Object Storage), Docker"])
    story += box("СОВЕТ", "Для пробы достаточно любого компьютера с Python: без бота, без HTTPS, без базы — "
                          "сайт и склад работают на SQLite «из коробки».")

    # ---------- 3 ----------
    story += h1(3, "Установка «из коробки» (4 способа)")
    story.append(Paragraph("3.1. Локально / на любом сервере — мастер setup.sh", S["h2"]))
    story += code(
        "git clone https://github.com/t9206921155-sys/Magazin_site_sklad_apk.git\n"
        "cd Magazin_site_sklad_apk\n"
        "./setup.sh                        # мастер: deps + .env + бот + запуск\n"
        "./setup.sh --venv --test          # с venv и прогоном тестов\n"
        "./setup.sh --no-run               # только установить\n"
        "./setup.sh --check                # проверить установку",
        "терминал")
    story.append(p("Мастер сам проверит Python, поставит зависимости, задаст 5 вопросов "
                   "(домен, токен бота, ID админов, пароль, оплата), создаст "
                   "<font name='DVM'>telegram-shop/.env</font> с надёжными секретами, предложит настроить "
                   "Telegram-бота и запустит сервер на <font name='DVM'>:8000</font>. Останов — Ctrl+C. "
                   "Старый <font name='DVM'>install.sh</font> работает как раньше. Подробнее — SETUP-AUTO.md."))
    story.append(Paragraph("3.2. Вручную (прозрачно, по шагам)", S["h2"]))
    story += code(
        "cd telegram-shop\n"
        "pip install -r requirements.txt\n"
        "cp .env.example .env      # заполните BOT_TOKEN, ADMIN_IDS, WEBAPP_URL\n"
        "python bot.py             # бот отключён? сайт всё равно работает",
        "терминал")
    story.append(Paragraph("3.3. Docker", S["h2"]))
    story += code("docker compose up -d --build", "терминал")
    story.append(Paragraph("3.4. Production-VPS (nginx + systemd + HTTPS)", S["h2"]))
    story += code(
        "git clone https://github.com/t9206921155-sys/Magazin_site_sklad_apk.git && cd Magazin_site_sklad_apk\n"
        "sudo -E ./setup.sh --vps --domain shop.example.com \\\n"
        "  --bot-token 123456:AA... --admin-ids 123456789 --bot-mode webhook\n"
        "# HTTPS: добавьте LETSENCRYPT_EMAIL=you@example.com\n"
        "# дальше из сводки: smoke → setup_bot.py → build-apps.sh",
        "терминал (на VPS)")
    story.append(p("Мастер VPS ставит пакеты, код в <font name='DVM'>/opt/magazin-shop</font>, venv, "
                   "настраивает <font name='DVM'>.env</font> (вопросы или переменные SETUP_*), systemd, nginx, HTTPS, "
                   "таймеры бэкапов и watchdog. Ручное заполнение .env больше не требуется."))
    story += box("ВАЖНО", "Смените пароль склада и админки: в .env — ADMIN_PASSWORD (по умолчанию admin123), "
                          "в складе: Настройки → Сотрудники → задайте пароли сотрудникам.")

    # ---------- 4 ----------
    story += h1(4, "Файл .env: все переменные с примерами")
    story.append(p("Файл <font name='DVM'>telegram-shop/.env</font> читается при старте. Шаблон — <font name='DVM'>.env.example</font>; "
                   "для VPS — <font name='DVM'>.env.production.example</font>."))
    story += table(
        ["Переменная", "Пример значения", "Зачем"],
        [["BOT_TOKEN", "123456:AA…", "токен бота от @BotFather; пусто = бот выключен"],
         ["ADMIN_IDS", "123456789,987654321", "Telegram ID администраторов"],
         ["ADMIN_PASSWORD", "S3cret!", "пароль веб-админки /admin (смените!)"],
         ["WEBAPP_URL", "https://shop.example.com", "публичный HTTPS-адрес: кнопка меню, webhook, QR"],
         ["PAYMENT_PROVIDER", "yookassa | tbank | cryptobot", "приём платежей"],
         ["BOT_MODE", "polling | webhook", "polling — без домена; webhook — на production"],
         ["WEBHOOK_PATH", "/tg/webhook", "путь приёма апдейтов Telegram"],
         ["WEBHOOK_SECRET", "случайная строка", "защита вебхука (openssl rand -hex 24)"],
         ["HOST / PORT", "0.0.0.0 / 8000", "адрес и порт сервера"],
         ["CORS_ORIGINS", "https://shop.example.com", "источники для Mini App/PWA (или * для разработки)"],
         ["TRUSTED_HOSTS", "shop.example.com", "разрешённые Host; пусто = любые (только dev!)"],
         ["RATE_LIMIT_1C / RATE_LIMIT_API", "120 / 600", "лимиты запросов в минуту"],
         ["AUTH_RATE_LIMIT", "20", "попыток входа на склад в минуту с одного IP"],
         ["WH_SESSION_TTL_DAYS", "30", "срок жизни сессии склада"],
         ["DISK_FREE_MIN_MB", "500", "порог предупреждения о месте на диске"],
         ["METRICS_TOKEN", "случайная строка", "доступ к /metrics"],
         ["MAGAZIN_DB", "data/shop.db", "путь к БД SQLite (или строка подключения)"],
         ["DATABASE_PROVIDER", "vps | mysql | supabase_direct | supabase_proxy", "тип базы (см. STORAGE-ARCHITECTURE.md)"]],
        [42 * mm, 55 * mm, 71 * mm])
    story += code(
        "# сгенерировать стойкие секреты:\nopenssl rand -hex 24   # WEBHOOK_SECRET\nopenssl rand -hex 16   # METRICS_TOKEN",
        "пример")

    # ---------- 5 ----------
    story += h1(5, "Telegram-бот и Mini App")
    story += li(["@BotFather → /newbot → получите BOT_TOKEN → впишите в .env",
                 "Узнайте свой Telegram ID (например @userinfobot) → впишите в ADMIN_IDS",
                 "WEBAPP_URL = ваш публичный HTTPS-адрес (для localhost оставьте пустым — будет polling)",
                 "BOT_MODE=webhook — на production (нужен HTTPS); polling — для разработки",
                 "Меню бота: @BotFather → /setmenubutton → адрес https://ваш-домен/app"])
    story += box("ПРИМЕР", "Минимальный запуск бота на домашнем ПК: BOT_TOKEN=…; BOT_MODE=polling (по умолчанию); "
                           "WEBAPP_URL пустой. Ссылка на магазин в боте откроет страницу-заглушку, но команды работают.")

    # ---------- 6 ----------
    story += h1(6, "Склад: вход, роли, мультисклад")
    story += table(["Действие", "Как"],
                   [["Войти", "<font name='DVM'>/warehouse/</font> → логин <b>admin</b> / пароль <b>admin123</b> (смените!)"],
                    ["Сменить пароль админа", "ADMIN_PASSWORD в .env (веб-админ) или Настройки → Сотрудники"],
                    ["Добавить сотрудника", "Настройки → Сотрудники → создать логин/пароль → выдать склад(ы)"],
                    ["Права", "Сотрудник видит только назначенные склады; запись на чужой = 403"],
                    ["Мультисклад", "Настройки → Склады: создание, перемещения (списание/приход атомарны)"],
                    ["Приёмка/продажа", "Скан кода → количество → Приход/Продажа; офлайн-операции уходят очередью"]],
                   [45 * mm, 123 * mm])

    # ---------- 7 ----------
    story += h1(7, "Сканеры штрих-кодов (HID, ТСД, камера)")
    story += table(["Способ", "Настройка"],
                   [["USB/Bluetooth-сканер (HID)", "Ничего настраивать не нужно: работает «из коробки» — сканер печатает код + Enter. "
                     "Проверка: на странице склада фокус в поле, сканируем — товар найден."],
                    ["Камера телефона", "Кнопка сканера → «Камера» (в браузере — запрос доступа, в APK — разрешение)"],
                    ["Нативный сканер APK", "Кнопка «Сканировать» в APK открывает камеру с распознаванием"],
                    ["ТСД / терминал (intent)", "Настроить в ТСД отправку intent: <font name='DVM'>sklad://scan?code={CODE}&mode=search</font> — "
                     "приложение получит код как скан (с вибро-фидбеком)"]],
                   [45 * mm, 123 * mm])
    story += box("ПРИМЕР", "Настройка DataWedge (Zebra): Intent → Action = android.intent.action.VIEW, "
                "Data = sklad://scan?code=%s&mode=search. Вместо %s ТСД подставит отсканированное значение.")

    # ---------- 8 ----------
    story += h1(8, "Печать этикеток: ZPL/EPL, IP-принтер, Wi-Fi с телефона")
    story.append(p("Термопринтеры (Zebra, Xprinter и др. с эмуляцией ZPL/EPL): выберите товары → Печать → профиль принтера."))
    story += table(["Профиль", "Поля", "Пример"],
                   [["Название", "Zebra GK420t", "любое"],
                    ["Формат", "zpl или epl", "zpl — большинство Zebra"],
                    ["Ширина/высота, мм", "58 × 40", "размер этикетки"],
                    ["Копий", "1", "сколько меток на товар"],
                    ["IP-адрес", "192.168.1.50", "IP принтера в Wi-Fi/LAN (порт 9100)"]],
                   [35 * mm, 55 * mm, 78 * mm])
    story += li(["<b>Серверная печать:</b> кнопка «Печать» — сервер сам шлёт ZPL на IP принтера (POST <font name='DVM'>/api/warehouse/print/network</font>)",
                 "<b>Печать с телефона (новое в 1.1.0):</b> кнопка «📱 Wi-Fi» — ZPL летит на принтер напрямую с телефона. "
                 "Работает, когда телефон и принтер в одной Wi-Fi-сети, а сервер — в интернете (и наоборот)",
                 "<b>PDF-этикетки/ценники:</b> кнопка скачивания — файл в «Загрузки» (в APK сохраняется нативно)",
                 "<b>.prn-файл:</b> можно скачать и скормить принтеру вручную"])
    story += box("ПРИМЕР", "Узнать IP принтера: на Zebra — удержать Feed (отпечатает конфиг), в веб-интерфейсе роутера — "
                "список DHCP. Проверка связи с ПК: ping 192.168.1.50, telnet 192.168.1.50 9100.")
    story += code(
        "# печать напрямую из консоли сервера (проверка принтера):\n"
        "printf '^XA^FO50,50^A0N,40,40^FDHello^FS^XZ' | nc 192.168.1.50 9100",
        "терминал (nc = netcat)")

    # ---------- 9 ----------
    story += h1(9, "Android APK «Склад 1.1.0»")
    story.append(Paragraph("9.1. Где скачать (3 способа)", S["h2"]))
    story += table(["Способ", "Адрес/путь"],
                   [["Страница с QR", "<font name='DVM'>https://ваш-сервер/download/android</font> — откройте на телефоне, сканируйте QR"],
                    ["Прямая ссылка", "<font name='DVM'>https://ваш-сервер/apk/Sklad-1.1.0-release.apk</font>"],
                    ["Из приложения", "Установленная версия сама предложит «Скачать обновление» (запрос к /api/releases/android)"],
                    ["Из репозитория", "<font name='DVM'>telegram-shop/apk/Sklad-1.1.0-release.apk</font> (+ .aab в telegram-shop/aab/)<br/>" +
                     "Покупательское «Магазин 1.0.0»: <font name='DVM'>/download/app</font> (+ Shop-*.apk в telegram-shop/apk/)"]],
                   [42 * mm, 126 * mm])
    story.append(Paragraph("9.2. Установка и подключение", S["h2"]))
    story += li(["Разрешите установку из источника (настройки Android → Безопасность)",
                 "При первом запуске: экран настройки → введите адрес сервера <font name='DVM'>https://ваш-сервер/warehouse/</font> → Подключить",
                 "Или отсканируйте QR со страницы <font name='DVM'>/download/android</font> — откроется deep link <font name='DVM'>sklad://connect?url=…</font>",
                 "Войдите под учёткой сотрудника склада (см. раздел 6)"])
    story.append(Paragraph("9.3. Что нового в 1.1.0 (versionCode 8)", S["h2"]))
    story += table(["Фича", "Как пользоваться"],
                   [["Файлы в «Загрузки»", "Этикетки PDF/.prn, ценники, отчёты, экспорт — сохраняются в папку Загрузки"],
                    ["Печать с телефона", "Кнопка «📱 Wi-Fi» у принтера: ZPL/EPL напрямую на принтер по Wi-Fi"],
                    ["Экран не гаснет", "Настройки склада → тумблер «Экран не гаснет во время работы»"],
                    ["Вибро на скан", "Автоматически после успешного сканирования"],
                    ["Экран ошибки сети", "Вместо всплывашки — экран «Сервер недоступен» с кнопкой «Повторить»"],
                    ["Сканы от ТСД", "Принимает intent/deep link <font name='DVM'>sklad://scan?code=…</font>"]],
                   [45 * mm, 123 * mm])
    story += box("ВАЖНО", "Обновление 1.0.6 → 1.1.0 ставится поверх без удаления: подпись приложения не менялась. "
                          "Данные сервера не затрагиваются.")

    # ---------- 10 ----------
    story += h1(10, "Обмен с 1С")
    story.append(p("Маршруты: <font name='DVM'>GET /1c/catalog</font>, <font name='DVM'>GET /1c/stock</font>, "
                   "<font name='DVM'>POST /1c/stock</font> (остатки/цены), <font name='DVM'>GET /1c/orders</font>. "
                   "Авторизация — заголовок <font name='DVM'>X-1C-Token</font> (токен: Админка → Настройки → «Сбросить токен 1С»))."))
    story += code(
        'curl -X POST https://shop.example.com/1c/stock \\\n'
        '  -H "X-1C-Token: ВАШ_ТОКЕН" -H "Content-Type: application/json" \\\n'
        '  -d \'{"items":[{"code":"ABC-001","stock":47,"price":777}]}\'' + "\n\n"
        '# ответ: {"updated":1,"failed":[],"not_found":[]}',
        "пример обновления остатка и цены из 1С")
    story += box("ВАЖНО", "Пустой stock=0 снимает товар с продажи. Лимит — 5000 позиций в пакете, "
                          "неизвестные коды попадают в not_found и не ломают пакет.")

    # ---------- 11 ----------
    story += h1(11, "Маркетплейс и кабинет продавца")
    story += li(["Продавец регистрируется через <font name='DVM'>/seller</font> (или его создаёт админ)",
                 "Витрина, товары, офферы к чужим товарам, чат покупателя, рейтинг продавца",
                 "Безопасная сделка: деньги удерживаются до подтверждения получения покупателем",
                 "Подписки и бусты объявлений — тарифы в админке (Marketplace 2.0)",
                 "Модерация: жалобы, бан продавца, скрытие товаров — в /admin"])

    # ---------- 12 ----------
    story += h1(12, "SEO и продвижение")
    story += li(["<font name='DVM'>/sitemap.xml</font> — генерируется автоматически (товары/категории/блог, lastmod)",
                 "<font name='DVM'>/robots.txt</font> — закрывает служебные разделы",
                 "Микроразметка и SSR-страницы каталога — из коробки",
                 "Campaign Manager (блок 24): кампании создаются как <b>draft</b>; ручной approve → внешний провайдер "
                 "забирает publication package. Реальные публикации включаются только после проверки API площадок",
                 "UTM-разметка ссылок — автоматическая, проверка: python3 -m pytest -q tests/test_utm_builder.py"])

    # ---------- 13 ----------
    story += h1(13, "Безопасность и HTTPS")
    story += table(["Мера", "Как включить"],
                   [["HTTPS", "deploy/bootstrap-vps.sh ставит nginx + certbot автоматически (домен обязателен)"],
                    ["TRUSTED_HOSTS", ".env: список доменов через запятую — защита от Host-header атак"],
                    ["CORS_ORIGINS", ".env: домен Mini App/PWA (в production не оставляйте *)"],
                    ["Rate limits", "RATE_LIMIT_1C / RATE_LIMIT_API / AUTH_RATE_LIMIT — уже включены"],
                    ["Сессии склада", "WH_SESSION_TTL_DAYS — срок жизни, вход по логин/пароль сотрудника"],
                    ["Smoke-проверка", "./deploy/post-deploy-smoke.sh https://ваш-домен"],
                    ["Скан секретов", "deploy/secret-scan.sh"]],
                   [40 * mm, 128 * mm])

    # ---------- 14 ----------
    story += h1(14, "Резервные копии")
    story += code(
        "python3 telegram-shop/scripts/backup.py                 # локальный бэкап SQLite\n"
        "python3 telegram-shop/scripts/backup_sqlite_to_s3.py    # в S3/Яндекс Object Storage\n"
        "python3 telegram-shop/scripts/restore_sqlite.py backup.db.gz",
        "примеры (unit-файлы systemd: deploy/magazin-backup.timer)")
    story.append(p("Проверка восстановления — обязательный шаг production (блок 14/18): "
                   "backup без проверенного restore резервом не считается."))

    # ---------- 15 ----------
    story += h1(15, "Обновление системы и пересборка APK")
    story += li(["Обновление на VPS одной командой: <font name='DVM'>sudo ./setup.sh --update</font> — сначала бэкап "
                 "БД с ротацией, затем код, зависимости, рестарт, health и smoke",
                 "Тесты перед выкладкой: <font name='DVM'>bash run-tests.sh</font> (серверные сюиты + корневой "
                 "<font name='DVM'>pytest tests/</font>); быстрая проверка: <font name='DVM'>./setup.sh --check</font>",
                 "<b>APK пересобираются сами</b>: пуш в ветку → GitHub Actions собирает APK+AAB «Склада» и «Магазина» "
                 "и коммитит в репо (ci-build-apk.sh, ci-build-shop-apk.sh; повторной сборки нет, если версия не менялась)",
                 "Новая версия APK: поднять versionName/versionCode в build.gradle и в шапке rebuild-apk.sh "
                 "(или mobile/android-wrapper/build-apk.sh) → пуш",
                 "Локальная сборка с адресом сервера: <font name='DVM'>./deploy/build-apps.sh --url https://ваш-домен</font>",
                 "Телефон увидит обновление через «Скачать обновление» в приложении"])

    # ---------- 16 ----------
    story += h1(16, "Диагностика и FAQ")
    story += table(["Симптом", "Решение"],
                   [["Порт 8000 занят", "В .env другой PORT или убить процесс: fuser -k 8000/tcp"],
                    ["Бот молчит", "Проверьте BOT_TOKEN; без WEBAPP_URL работает только polling"],
                    ["Склад 403 при входе", "Не тот логин/пароль; AUTH_RATE_LIMIT — не более 20 попыток в минуту с IP"],
                    ["1С отдаёт 403", "Не совпадает X-1C-Token (пересоздайте токен в админке)"],
                    ["Принтер не печатает с сервера", "Сервер и принтер в разных сетях → используйте кнопку «📱 Wi-Fi» на телефоне"],
                    ["APK не видит обновление", "На телефоне тот же сервер? Проверьте /api/releases/android — там version 1.1.0"],
                    ["Скачанные файлы не открываются", "В APK 1.1.0 файлы падают в «Загрузки» (Downloads) — ищите там"],
                    ["Ошибки после git pull", "pip install -r requirements.txt; python3 -m py_compile *.py; bash run-tests.sh"]],
                   [58 * mm, 110 * mm])
    story.append(Spacer(1, 6))
    story += box("СОВЕТ", "Полные эксплуатационные документы: telegram-shop/STEP-BY-STEP-RUNBOOK.md, "
                          "PRODUCTION-SETUP.md, WAREHOUSE-EMPLOYEE-GUIDE.md, OWNER-ADMIN-SETUP.md, APK-TEST-CHECKLIST.md.")

    doc.build(story)
    print("OK:", OUT, f"({os.path.getsize(OUT)} bytes)")


if __name__ == "__main__":
    sys.exit(build())
