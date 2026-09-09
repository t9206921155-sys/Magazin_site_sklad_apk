#!/usr/bin/env bash
# ============================================================
#  Сборка дистрибутива Telegram Shop «всё в одном»:
#   исходники + PDF-руководство + install.sh + APK/AAB «Склад».
#
#  Запуск:  ./build-distr.sh [версия]     (по умолчанию — из apk-build/rebuild-apk.sh)
#  Результат: distr/Telegram-Shop-<версия>.zip
# ============================================================
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

VERSION="$(sed -n 's/^APP_VERSION="\([^"]*\)"/\1/p' telegram-shop/apk-build/rebuild-apk.sh | head -1)"
[ -n "${1:-}" ] && VERSION="$1"
[ -n "$VERSION" ] || { echo "не определил версию"; exit 1; }

NAME="Telegram-Shop-${VERSION}"
OUT_DIR="$ROOT/distr"
OUT="$OUT_DIR/${NAME}.zip"

command -v git >/dev/null || { echo "нужен git"; exit 1; }
mkdir -p "$OUT_DIR"

log(){ printf '\033[1;36m==>\033[0m %s\n' "$*"; }

log "Собираю ${NAME}.zip из HEAD ($(git rev-parse --short HEAD))"
rm -f "$OUT"
# чистое дерево из git (без мусора) + запакованное PDF-руководство уже в docs/ (tracked)
git archive --format=zip --prefix="${NAME}/" -o "$OUT" HEAD

APK="telegram-shop/apk/Sklad-${VERSION}-release.apk"
AAB="telegram-shop/aab/Sklad-${VERSION}-release.aab"
if [ -f "$APK" ] && [ -f "$AAB" ]; then
  log "APK/AAB ${VERSION} уже в дереве — включены автоматически"
else
  log "ВНИМАНИЕ: ${APK} и/или ${AAB} не найдены — в дистрибутиве не будет APK"
fi

# самопроверка: PDF, install.sh и APK на месте внутри архива (unzip портит кириллицу — проверяем python'ом)
python3 - "$OUT" <<'PY'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
names = z.namelist()
prefix = names[0].split("/")[0] + "/"
need = ["install.sh", "README.md", "run-tests.sh", "docs/Telegram-Shop-руководство.pdf",
        "telegram-shop/apk/Sklad-1.1.0-release.apk"]
missing = [f for f in need if prefix + f not in names]
if missing:
    print("в архиве нет:", ", ".join(missing)); sys.exit(1)
print("самопроверка архива: OK")
PY

log "Готово: $OUT ($(du -h "$OUT" | cut -f1))"
echo    "Состав: исходники + docs/Telegram-Shop-руководство.pdf + install.sh + APK/AAB «Склад ${VERSION}»"
echo    "Установка получателем: unzip ${NAME}.zip && cd ${NAME} && ./install.sh"
