"""Тесты генераторов этикеток и ценников (Этап 4 склада).

Запуск:  cd telegram-shop && python3 tests-labels.py
"""
import sys

import pdfreport as r

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  \u2705 {name}")
    else:
        failed += 1
        print(f"  \u274c {name}")


DANGER = {
    "id": 1,
    "name": 'Кабель ^XZ 3" ~JA',
    "price": 99,
    "barcode": "4600000000999",
    "storage_location": "B-2",
    "owner_name": "Петров",
}

NORMAL = {
    "id": 2,
    "name": "Наушники",
    "price": 2990,
    "old_price": 4990,
    "barcode": "4600000000555",
    "sku": "SALE-1",
    "storage_location": "C-12",
}

print("1) ZPL: инъекция управляющих символов")
z = r.labels_zpl([DANGER])
ok("ровно одна метка (^XZ не размножился)", z.count("^XZ") == 1)
ok("команда ~JA обезврежена", "~JA" not in z)
ok("^ из названия вырезан", "^XZ 3" not in z.split("^FS")[1])
ok("штрих-код на месте", "4600000000999" in z)

print("2) EPL: экранирование кавычек")
e = r.labels_epl([DANGER])
ok('кавычка экранирована', '\\"' in e)
ok("штрих-код на месте", "4600000000555" not in e and "4600000000999" in e)

print("3) Формат цены")
ok("целая цена без хвоста", r._fmt_price(1234.0) == "1234")
ok("дробная сохраняет копейки", r._fmt_price(1234.5) == "1234.50")
ok("None -> 0", r._fmt_price(None) == "0")
ok("мусор -> 0", r._fmt_price("abc") == "0")

print("4) copies")
z2 = r.labels_zpl([DANGER], copies=3)
ok("3 копии в ZPL", z2.count("^XA") == 3)
e2 = r.labels_epl([DANGER], copies=3)
ok("EPL P3,1", "P3,1" in e2)
e3 = r.labels_epl([DANGER], copies=0)
ok("copies=0 не ломает EPL", "P1,1" in e3)

print("5) PDF-наклейки")
pdf = r.labels_pdf([DANGER, NORMAL])
ok("PDF сгенерирован", pdf[:4] == b"%PDF" and len(pdf) > 1000)

print("6) PDF-ценники")
tags = r.price_tags_pdf([NORMAL], show_qr=True, shop_name="Тест-магазин")
ok("ценник сгенерирован", tags[:4] == b"%PDF" and len(tags) > 1000)
tags_noqr = r.price_tags_pdf([NORMAL], show_qr=False)
ok("без QR тоже работает", tags_noqr[:4] == b"%PDF")
many = r.price_tags_pdf([NORMAL] * 40, copies=2)
ok("многостраничная пачка", many[:4] == b"%PDF" and len(many) > len(tags))
try:
    r.price_tags_pdf([])
    ok("пустой список -> ValueError", False)
except ValueError:
    ok("пустой список -> ValueError", True)

print("7) Длинное название не роняет генератор")
long_p = dict(NORMAL, name="Ы" * 300)
ok("очень длинное имя", r.price_tags_pdf([long_p])[:4] == b"%PDF")
ok("длинное имя в ZPL обрезано до 40", len(
    [ln for ln in r.labels_zpl([long_p]).splitlines() if "A0N,22,22" in ln][0]) < 120)

print(f"\nИтог: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
