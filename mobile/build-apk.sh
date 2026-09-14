#!/usr/bin/env bash
# ============================================================
#  mobile/build-apk.sh — теперь просто вызывает актуальную сборку
#  покупательского приложения (блок 25, Фаза 1):
#     mobile/android-wrapper/build-apk.sh [URL_ВИТРИНЫ]
#  Старая заглушка с echo удалена в блоке 29.
#  Для обеих сборок сразу: ./deploy/build-apps.sh --url https://...
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"
echo "-> mobile/android-wrapper/build-apk.sh $*" >&2
exec ./android-wrapper/build-apk.sh "$@"
