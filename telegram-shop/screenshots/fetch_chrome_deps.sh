#!/bin/bash
# Скачивает недостающие системные библиотеки для Chromium из Debian pool
# и распаковывает их в /tmp/chromedeps (без root).
set -u
DEST=/tmp/chromedeps
mkdir -p "$DEST"
cd "$DEST"

PKGS="
main/n/nspr
main/n/nss
main/libx/libxdamage
main/libx/libxkbcommon
main/a/alsa-lib
main/a/atk1.0
main/a/at-spi2-core
main/a/at-spi2-atk
main/c/cups
"

fetch_and_extract() {
  local dir="$1"
  local url="http://deb.debian.org/debian/pool/$dir/"
  echo "== $dir"
  local deb
  deb=$(curl -s "$url" | grep -oE 'href="[^"]+_amd64\.deb"' | sed 's/href="//;s/"//' | sort -V | tail -1)
  if [ -z "$deb" ]; then echo "  нет пакета"; return; fi
  echo "  -> $deb"
  curl -s -O "$url$deb" || { echo "  ошибка скачивания"; return; }
  local datafile
  datafile=$(ar t "$deb" | grep '^data\.tar' | head -1)
  if [ -z "$datafile" ]; then echo "  нет data.tar"; rm -f "$deb"; return; fi
  ar p "$deb" "$datafile" > "$datafile" 2>/dev/null
  case "$datafile" in
    *.xz) tar -xf "$datafile" -C "$DEST" ;;
    *.zst) tar --zstd -xf "$datafile" -C "$DEST" 2>/dev/null || { command -v zstd >/dev/null && zstd -d -c "$datafile" | tar -xf - -C "$DEST" || echo "  zstd не поддерживается"; } ;;
    *.gz) tar -xzf "$datafile" -C "$DEST" ;;
    *) tar -xf "$datafile" -C "$DEST" ;;
  esac
  rm -f "$datafile" "$deb"
}

for p in $PKGS; do
  fetch_and_extract "$p" || true
done

echo "=== итог ==="
find "$DEST/usr/lib" -name "*.so*" 2>/dev/null | sed "s|$DEST/||" | sort
