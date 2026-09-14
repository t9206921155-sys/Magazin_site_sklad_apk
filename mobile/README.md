# mobile/ — покупательское приложение

| Путь | Статус | Что это |
|---|---|---|
| `android-wrapper/` | ✅ актуально (блок 25, Фаза 1) | WebView-обёртка витрины: `ru.telegramshop.shop`, сборка `./android-wrapper/build-apk.sh [URL]` или `./deploy/build-apps.sh` |
| `ANDROID-APP-TZ.md` | ✅ актуально | Полное ТЗ: Фаза 1 + Фазы 2–6 (React Native) |
| `src/` | 🗄 архивный прототип | Ранние наброски экранов RN (возвращают объекты-описания, не UI). Оставлены для истории фаз 2–6, сборке не подлежат |
| `build-apk.sh` | ✅ редирект | Вызывает `android-wrapper/build-apk.sh` |
| `package.json` | 🗄 архив | Манифест прототипа; зависимости не ставятся |

Не запускайте `npm install` / `node src/App.js` — это не рабочее приложение.
