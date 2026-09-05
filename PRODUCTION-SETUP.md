# Production setup — краткая последовательность

1. На VPS установить Python и создать venv.
2. Клонировать репозиторий и установить `requirements.txt`.
3. Скопировать `.env.example` в `.env`; секреты хранить только на сервере.
4. Выбрать базу: для первого запуска `vps`/SQLite.
5. Подключить Object Storage и проверить `cloud/config-check`.
6. Запустить приложение под systemd или supervisor.
7. Настроить reverse proxy с HTTPS.
8. Ограничить `CORS_ORIGINS` конкретными origin.
9. Задать `METRICS_TOKEN` и закрыть `/metrics` через reverse proxy.
10. Запустить `deploy/post-deploy-smoke.sh`.
11. Сделать backup и проверить restore на копии.
12. Сохранить screenshots в соответствии с `DEVELOPER-MANUAL-VALIDATION.md`.

## Важные правила

- Не добавлять `.env`, токены и ключи в Git.
- Service-role Supabase key хранить только на VPS.
- OAuth Yandex Disk не помещать в APK или frontend.
- Фото и backup хранить в разных bucket/path.
- Перед миграцией MySQL остановить запись или использовать окно обслуживания.

## Автоматический deploy на VPS

Для VPS без Docker:

```bash
sudo -E DEPLOY_DOMAIN=https://YOUR-DOMAIN.example \
  ./deploy/auto-deploy-vps.sh
```

Скрипт создаёт `/opt/magazin-shop`, virtualenv и systemd-сервис `magazin-shop`. После первого запуска заполните `/opt/magazin-shop/telegram-shop/.env`, затем выполните:

```bash
sudo systemctl restart magazin-shop
sudo journalctl -u magazin-shop -n 100 --no-pager
```

Для повторного deploy скрипт делает fast-forward/reset до `origin/main`, устанавливает зависимости и перезапускает сервис. Не запускайте его поверх незакоммиченных production-изменений.
