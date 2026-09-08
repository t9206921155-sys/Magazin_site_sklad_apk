# Финальный статус автоматической части

## Готово

- CRM MVP и audit trail.
- Content jobs: prompt, queue, claim, callback, HMAC, review, approve/reject, retry, cancel.
- Campaign Manager: campaigns, channels, UTM, lifecycle, deduplication, bulk prepare/approve/dry-run, attribution.
- Provider boundaries: Telegram, VK, Avito, Meta/Instagram, TikTok, Wildberries.
- Stub/dry-run contract и diagnostics.
- SEO foundation: metadata helpers, robots, sitemap, UTM builder.
- Deployment preflight, secret scan, environment check, HTTPS check, rollback preflight.
- Smoke tests и инструкции.

## Требует ручной работы владельца

- Реальные OAuth apps, accounts, scopes и tokens.
- Staging publication по каждому provider.
- Wildberries seller/API audit.
- Production HTTPS, backup/restore и rollback.
- Yandex Webmaster, Google Search Console, indexing и Core Web Vitals.
- Production screenshots без secrets.

## Gate

Реальный publish остаётся отключённым до прохождения staging и ручного approval. Demo mode использует только stub/dry-run.
