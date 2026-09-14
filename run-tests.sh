#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# CI: дублируем весь вывод в файл — на Actions коммитим его в ветку для диагностики
if [ -n "${GITHUB_EVENT_NAME:-}" ]; then
  exec > >(tee /tmp/ci-run.log) 2>&1
fi
cd "$ROOT/telegram-shop"
TMP_DB="$(mktemp -p "${TMPDIR:-/tmp}" magazin-tests-XXXXXX.db)"; LOG="${TMP_DB}.log"
cleanup(){ [[ -n "${PID:-}" ]] && kill "$PID" 2>/dev/null || true; rm -f "$TMP_DB" "$LOG"; }
trap cleanup EXIT
PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"
BASE="http://127.0.0.1:$PORT"
export MAGAZIN_DB="$TMP_DB" BOT_TOKEN= PORT
python3 bot.py >"$LOG" 2>&1 & PID=$!
for i in {1..30}; do curl -sf "$BASE/" >/dev/null && break; sleep 1; done
status=0
python3 tests-health.py "$BASE" || status=1
python3 tests-storage-contracts.py || status=1
python3 tests-labels.py || status=1
node tests-hid-scanner.js || status=1
python3 tests-stage5.py "$BASE" || status=1
python3 tests-block06.py "$BASE" || status=1
python3 tests-block09.py "$BASE" || status=1
python3 tests-block13.py "$BASE" || status=1
# блок 14 (backup/restore/миграция): база — тот же $MAGAZIN_DB, что у сервера
MAGAZIN_DB="$MAGAZIN_DB" python3 tests-block14.py "$BASE" || status=1
python3 tests-block16.py "$BASE" || status=1
python3 tests-block19.py "$BASE" || status=1
python3 tests-block23.py "$BASE" || status=1
python3 tests-block25.py "$BASE" || status=1
python3 tests-block27.py "$BASE" || status=1
python3 tests-block29.py "$BASE" || status=1
# корневые pytest: маркетинг/SEO/провайдеры + установка из коробки (блок 28)
if ! python3 -m pytest --version >/dev/null 2>&1; then
  python3 -m pip install -q pytest 2>/dev/null || true
fi
if python3 -m pytest --version >/dev/null 2>&1; then
  (cd "$ROOT" && python3 -m pytest -q tests) || status=1
else
  echo "pytest недоступен — корневые тесты пропущены (pip install pytest)"
fi
# блок 15 — ПОСЛЕДНИМ из серверных: ставит IP в rate-карантин ~60с
python3 tests-block15.py "$BASE" || status=1
python3 scripts/check-env-keys.py || status=1
python3 -m py_compile *.py || status=1
for f in warehouse/*.js webapp/*.js; do node --check "$f" || status=1; done
# блок 26: после зелёных тестов собираем Android-релиз «Склад» (только на CI)
if [ "$status" = 0 ]; then
  bash "$ROOT/ci-build-apk.sh" || status=1
fi
# блок 25: после зелёных тестов собираем покупательское приложение (только на CI)
if [ "$status" = 0 ]; then
  bash "$ROOT/ci-build-shop-apk.sh" || status=1
fi
# CI: лог прогона — коммитом в ветку (диагностика + проверка прав на push)
if [ -n "${GITHUB_EVENT_NAME:-}" ] && [ -n "${GITHUB_REF_NAME:-}" ] && [ -f /tmp/ci-run.log ]; then
  cp /tmp/ci-run.log "$ROOT/ci-last-run.log"
  # 1) аннотации: хвост лога чанками в base64 (читаются через API даже без доступа к логам)
  tail -c 4200 /tmp/ci-run.log | base64 -w 640 > /tmp/ci-b64.txt
  n=0
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    echo "::notice::CILOG[$n] $line"
    n=$((n+1))
  done < /tmp/ci-b64.txt
  # 2) попытка закоммитить лог в ветку (проверка прав GITHUB_TOKEN на push)
  git -C "$ROOT" config user.email "actions@github.com"
  git -C "$ROOT" config user.name "github-actions[bot]"
  git -C "$ROOT" add -f ci-last-run.log
  if ! git -C "$ROOT" diff --cached --quiet; then
    git -C "$ROOT" commit -q -m "CI: лог прогона (status=$status) [skip ci]"
    git -C "$ROOT" push origin "HEAD:${GITHUB_REF_NAME}" \
      && echo "ci-report: лог запушен" \
      || echo "ci-report: push лога не удался (read-only GITHUB_TOKEN?)"
  fi
fi
exit "$status"
