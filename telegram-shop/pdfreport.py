"""Генерация PDF-отчётов маркетплейса (reportlab + DejaVu для кириллицы)."""
import io
import os

import config

FONT_REG = os.path.join(config.DATA_DIR, "fonts", "DejaVuSans.ttf")
FONT_BOLD = os.path.join(config.DATA_DIR, "fonts", "DejaVuSans-Bold.ttf")
# фолбэк на системные шрифты, если копии нет
for p, alt in ((FONT_REG, "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
               (FONT_BOLD, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")):
    if not os.path.exists(p) and os.path.exists(alt):
        FONT_REG = alt if p == FONT_REG else FONT_REG
        FONT_BOLD = alt if p == FONT_BOLD else FONT_BOLD


def commission_report_pdf(shop: str, date_from: str, date_to: str, rows: list, totals: dict,
                          payouts: list) -> bytes:
    """PDF-отчёт по комиссиям площадки за период."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    pdfmetrics.registerFont(TTFont("DejaVu", FONT_REG))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", FONT_BOLD))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Отчёт по комиссиям {shop}")

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1r", parent=styles["Title"], fontName="DejaVu-Bold",
                        fontSize=17, leading=22, spaceAfter=2)
    sub = ParagraphStyle("subr", parent=styles["Normal"], fontName="DejaVu",
                         fontSize=10, textColor=colors.HexColor("#64748b"), spaceAfter=12)
    h2 = ParagraphStyle("h2r", parent=styles["Heading2"], fontName="DejaVu-Bold",
                        fontSize=13, spaceBefore=8, spaceAfter=6)
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontName="DejaVu", fontSize=9.5, leading=13)
    cell_b = ParagraphStyle("cellb", parent=cell, fontName="DejaVu-Bold")
    cell_r = ParagraphStyle("cellr", parent=cell, alignment=2)

    period = (f"{date_from} — {date_to}") if date_from or date_to else "весь период"
    story = [
        Paragraph(f"Отчёт по комиссиям · {shop}", h1),
        Paragraph(f"Период: {period}", sub),
        Spacer(1, 2),
    ]

    # таблица продавцов
    data = [[Paragraph("Продавец", cell_b), Paragraph("Заказов", cell_b),
             Paragraph("Продажи, ₽", cell_b), Paragraph("Комиссия площадки, ₽", cell_b),
             Paragraph("К выплате, ₽", cell_b)]]
    for r in rows:
        data.append([
            Paragraph(r["store_name"], cell),
            Paragraph(str(r["orders"]), cell_r),
            Paragraph(f"{r['sales']:,}".replace(",", " "), cell_r),
            Paragraph(f"<font color='#16a34a'><b>{r['commission']:,}</b></font>".replace(",", " "), cell_r),
            Paragraph(f"{r['net']:,}".replace(",", " "), cell_r),
        ])
    t = totals or {}
    data.append([
        Paragraph("ИТОГО", cell_b),
        Paragraph("", cell),
        Paragraph(f"<b>{t.get('sales', 0):,}</b>".replace(",", " "), cell_r),
        Paragraph(f"<font color='#16a34a'><b>{t.get('commission', 0):,}</b></font>".replace(",", " "), cell_r),
        Paragraph(f"<b>{t.get('net', 0):,}</b>".replace(",", " "), cell_r),
    ])
    table = Table(data, colWidths=[62 * mm, 22 * mm, 30 * mm, 38 * mm, 32 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef2ff")),
    ]))
    story.append(table)

    # выплаты за период
    story.append(Paragraph("Выплаты продавцам за период", h2))
    paid = [p for p in payouts if p.get("status") == "paid"]
    if paid:
        pdata = [[Paragraph("Дата", cell_b), Paragraph("Продавец", cell_b), Paragraph("Сумма, ₽", cell_b)]]
        for p in paid:
            pdata.append([
                Paragraph((p.get("created_at") or "")[:10], cell),
                Paragraph(f"ID {p['seller_id']}", cell),
                Paragraph(f"{p['amount']:,}".replace(",", " "), cell_r),
            ])
        ptable = Table(pdata, colWidths=[40 * mm, 100 * mm, 44 * mm], repeatRows=1)
        ptable.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(ptable)
    else:
        story.append(Paragraph("Выплат за период не было.", cell))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Прибыль площадки за период: <b>{t.get('commission', 0) - t.get('payouts', 0):,}</b> ₽ "
        f"(комиссия {t.get('commission', 0):,} ₽ − выплаты {t.get('payouts', 0):,} ₽)".replace(",", " "),
        ParagraphStyle("res", parent=cell, fontName="DejaVu-Bold", fontSize=11, leading=15)))
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        f"Отчёт сформирован автоматически системой маркетплейса {shop}.", sub))

    doc.build(story)
    return buf.getvalue()


def _fmt_price(value) -> str:
    """Цена для этикетки: 1234.5 -> '1234.50', 1234.0 -> '1234'."""
    try:
        d = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    return f"{int(d)}" if d == int(d) else f"{d:.2f}"


def labels_pdf(products: list, width_mm: float = 58, height_mm: float = 40, copies: int = 1) -> bytes:
    """PDF-наклейки произвольного размера (для термопринтеров через драйвер или печать диалога)."""
    from reportlab.graphics.barcode import code128
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Table, TableStyle

    pdfmetrics.registerFont(TTFont("DejaVu", FONT_REG))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", FONT_BOLD))

    class BarcodeFlow(Flowable):
        def __init__(self, value, width=44 * mm, height=8 * mm):
            super().__init__()
            self.value = value
            self.width = width
            self.height = height

        def draw(self):
            bc = code128.Code128(self.value, barHeight=self.height * 0.75, barWidth=0.35,
                                 humanReadable=True)
            bc.drawOn(self.canv, 0, 0)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=8 * mm, rightMargin=8 * mm,
                            topMargin=8 * mm, bottomMargin=8 * mm)
    styles = getSampleStyleSheet()
    name_st = ParagraphStyle("nm", parent=styles["Normal"], fontName="DejaVu-Bold",
                             fontSize=9, leading=11)
    meta_st = ParagraphStyle("mt", parent=styles["Normal"], fontName="DejaVu",
                             fontSize=7.5, leading=9, textColor=colors.HexColor("#475569"))

    items = []
    for p in products:
        for _ in range(max(1, copies)):
            code = str(p.get("barcode") or p.get("code") or f"TG-{p['id']}")
            items.append([
                BarcodeFlow(code),
                Paragraph(p["name"][:60], name_st),
                Paragraph(f"{p.get('storage_location') or '—'} · {p.get('owner_name') or '—'} · "
                          f"{_fmt_price(p.get('price'))} ₽", meta_st),
            ])
    if not items:
        items = [[Paragraph("Нет товаров для печати", meta_st), "", ""]]

    cols = max(1, int((180 * mm) // (width_mm * mm)))  # сколько наклеек влезает по ширине A4
    rows = [items[i:i + cols] for i in range(0, len(items), cols)]
    data = []
    for chunk in rows:
        row = []
        for c in chunk:
            row.extend(c)
        while len(row) < cols * 3:
            row.append("")
        data.append(row)
    t = Table(data, colWidths=[width_mm * mm] * cols)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    doc.build([t])
    return buf.getvalue()


def _zpl_escape(text: str) -> str:
    """Обезвреживает управляющие символы ZPL.

    В ZPL '^' и '~' начинают команду, а '\\' экранирует. Без очистки товар
    с названием вида 'Кабель ^XZ ~JA' обрывает этикетку и может отменить
    задания печати на принтере (^XZ — конец метки, ~JA — cancel all).
    """
    return (str(text or "")
            .replace("\\", " ")
            .replace("^", " ")
            .replace("~", " ")
            .replace("\r", " ")
            .replace("\n", " "))


def _epl_escape(text: str) -> str:
    """EPL: строки в кавычках, поэтому '"' и '\\' экранируются обратным слешем."""
    return (str(text or "")
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\r", " ")
            .replace("\n", " "))


def labels_zpl(products: list, width_mm: float = 58, height_mm: float = 40, copies: int = 1) -> str:
    """ZPL-этикетки для Zebra (GP/ZD серии) — файл .prn, отправка напрямую на принтер."""
    out = []
    dpi = 203
    w = int(width_mm / 25.4 * dpi)   # ширина в точках
    h = int(height_mm / 25.4 * dpi)  # высота в точках
    for p in products:
        code = _zpl_escape(p.get("barcode") or p.get("code") or f"TG-{p['id']}")
        name = _zpl_escape((p["name"] or "")[:40].upper())
        meta = _zpl_escape(
            f"{p.get('storage_location') or '-'} | {p.get('owner_name') or '-'} | "
            f"{_fmt_price(p.get('price'))} RUB")
        block = (
            f"^XA^PW{w}^LL{h}^CI28\n"
            f"^FO10,10^A0N,22,22^FD{name}^FS\n"
            f"^FO10,42^BY2,2,40^BCN,40,Y,N,N^FD{code}^FS\n"
            f"^FO10,95^A0N,18,18^FD{meta}^FS\n"
            f"^FO{w - 90},42^BQN,2,5^FDLA,{code}^FS\n"
            f"^XZ"
        )
        for _ in range(max(1, copies)):
            out.append(block)
    return "\n".join(out) + "\n"


def labels_epl(products: list, width_mm: float = 58, height_mm: float = 40, copies: int = 1) -> str:
    """EPL-этикетки для Eltron/ОВЕН — файл .prn (старые термопринтеры)."""
    dpi = 203
    w = int(width_mm / 25.4 * dpi)
    h = int(height_mm / 25.4 * dpi)
    blocks = []
    for p in products:
        code = _epl_escape(p.get("barcode") or p.get("code") or f"TG-{p['id']}")
        name = _epl_escape((p["name"] or "")[:40])
        meta = _epl_escape(
            f"{p.get('storage_location') or '-'} | {p.get('owner_name') or '-'} | "
            f"{_fmt_price(p.get('price'))} RUB")
        blocks.append(
            f"N\n"
            f"q{w}\nQ{h},0\n"
            f"A10,10,0,2,1,1,N,\"{name}\"\n"
            f"B10,45,0,1,2,2,40,B,\"{code}\"\n"
            f"A10,105,0,1,1,1,N,\"{meta}\"\n"
            f"P{max(1, copies)},1\n"
        )
    return "\n".join(blocks)


def price_tags_pdf(products: list, width_mm: float = 58, height_mm: float = 40,
                   copies: int = 1, show_qr: bool = True, shop_name: str = "") -> bytes:
    """Ценники для торгового зала: крупная цена, название, старая цена и скидка, QR.

    Отличие от labels_pdf: та печатает складские наклейки (упор на штрих-код),
    здесь упор на цену для покупателя.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as pdfcanvas

    pdfmetrics.registerFont(TTFont("DejaVu", FONT_REG))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", FONT_BOLD))

    W = max(30.0, min(120.0, float(width_mm))) * mm
    H = max(20.0, min(120.0, float(height_mm))) * mm
    margin = 6 * mm

    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4
    cols = max(1, int((page_w - 2 * margin) // W))
    rows = max(1, int((page_h - 2 * margin) // H))
    per_page = cols * rows

    expanded = []
    for p in products:
        for _ in range(max(1, min(9, int(copies or 1)))):
            expanded.append(p)
    if not expanded:
        raise ValueError("Нет товаров для печати ценников")

    qr_mod = None
    if show_qr:
        try:
            import qrcode as _qr
            qr_mod = _qr
        except ImportError:
            qr_mod = None

    def shrink(text, font, start, max_w):
        """Подбирает размер шрифта, чтобы строка влезла в ширину."""
        size = start
        while size > 5 and pdfmetrics.stringWidth(text, font, size) > max_w:
            size -= 0.5
        return size

    for idx, p in enumerate(expanded):
        pos = idx % per_page
        if idx and pos == 0:
            c.showPage()
        col, row = pos % cols, pos // cols
        x = margin + col * W
        y = page_h - margin - (row + 1) * H

        c.setLineWidth(0.4)
        c.setDash(1, 2)
        c.rect(x, y, W, H)
        c.setDash()

        pad = 3 * mm
        inner = W - 2 * pad
        top = y + H - pad

        if shop_name:
            c.setFont("DejaVu", 6)
            c.drawString(x + pad, top - 5, shop_name[:38])
            top -= 7

        name = (p.get("name") or "")[:60]
        fs = shrink(name, "DejaVu-Bold", 9, inner)
        c.setFont("DejaVu-Bold", fs)
        c.drawString(x + pad, top - fs, name)
        top -= fs + 3

        price = _fmt_price(p.get("price"))
        old = p.get("old_price") or p.get("price_old") or 0
        try:
            old_f = float(old or 0)
        except (TypeError, ValueError):
            old_f = 0.0
        try:
            cur_f = float(p.get("price") or 0)
        except (TypeError, ValueError):
            cur_f = 0.0

        price_txt = f"{price} \u20bd"
        pfs = shrink(price_txt, "DejaVu-Bold", 26, inner)
        c.setFont("DejaVu-Bold", pfs)
        baseline = y + pad + 9 * mm
        c.drawString(x + pad, baseline, price_txt)

        if old_f > cur_f > 0:
            old_txt = f"{_fmt_price(old_f)} \u20bd"
            c.setFont("DejaVu", 8)
            ow = pdfmetrics.stringWidth(old_txt, "DejaVu", 8)
            ox = x + pad
            oy = baseline - 10
            c.drawString(ox, oy, old_txt)
            c.setLineWidth(0.7)
            c.line(ox, oy + 2.5, ox + ow, oy + 2.5)
            disc = int(round((old_f - cur_f) / old_f * 100))
            c.setFont("DejaVu-Bold", 8)
            c.drawString(ox + ow + 4, oy, f"-{disc}%")

        meta_bits = [b for b in (p.get("sku"), p.get("storage_location")) if b]
        if meta_bits:
            c.setFont("DejaVu", 6)
            c.drawString(x + pad, y + pad, " · ".join(str(b) for b in meta_bits)[:40])

        code = str(p.get("barcode") or p.get("code") or f"TG-{p.get('id', '')}")
        if qr_mod and code:
            try:
                img = qr_mod.make(code)
                side = min(14 * mm, H - 2 * pad)
                tmp = io.BytesIO()
                img.save(tmp, format="PNG")
                tmp.seek(0)
                from reportlab.lib.utils import ImageReader
                c.drawImage(ImageReader(tmp), x + W - pad - side, y + pad,
                            width=side, height=side, mask="auto")
            except Exception:
                pass

    c.save()
    return buf.getvalue()
