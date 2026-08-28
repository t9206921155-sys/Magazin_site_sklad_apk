#!/bin/bash
set -e
echo "=== Деплой Telegram Shop ==="
docker-compose down || true
docker-compose build --no-cache
docker-compose up -d
echo "=== Деплой завершён. Сервис доступен на порту 80 (nginx) → 8000 (web). ==="
