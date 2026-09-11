package ru.telegramshop.shop;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

/**
 * «Магазин» — покупательское Android-приложение (блок 25, Фаза 1).
 * WebView-обёртка витрины: каталог, корзина и оплата работают через сайт.
 *
 * Поддерживает:
 * - ввод адреса витрины при первом запуске,
 * - импорт адреса через deep link: shop://setup?url=https://site/
 * - мгновенное подключение через deep link: shop://connect?url=https://site/
 * - shop://install — открыть страницу скачивания APK (/download/app) в браузере,
 * - мягкий баннер обновления по /api/app/version при старте,
 * - выбор изображений в web-формах (например, фото к обращению),
 * - экран ошибки сети с кнопкой «Повторить»,
 * - настройки подключения по долгому нажатию на экране магазина.
 */
public class MainActivity extends AppCompatActivity {

    private static final String PREFS = "shop_prefs";
    private static final String KEY_URL = "server_url";
    private static final int REQ_FILE = 2001;
    private static final String APP_UA = " ShopApp/1.0.0";

    private WebView webView;
    private View mainView, setupView, errorWrap;
    private LinearLayout updateBanner;
    private EditText urlInput;
    private TextView setupError, appMeta, setupHint, updateInfo, errorText, bannerText;
    private Button btnConnect, btnBack, btnReset, btnUpdate, btnRetry, btnBannerUpdate, btnBannerClose;
    private SharedPreferences prefs;
    private String baseUrl = "";
    private String latestUpdateUrl = "";
    private ValueCallback<Uri[]> filePathCallback;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        mainView = findViewById(R.id.main_wrap);
        setupView = findViewById(R.id.setup_wrap);
        webView = findViewById(R.id.webview);
        updateBanner = findViewById(R.id.update_banner);
        urlInput = findViewById(R.id.url_input);
        setupError = findViewById(R.id.setup_error);
        setupHint = findViewById(R.id.setup_hint);
        appMeta = findViewById(R.id.app_meta);
        updateInfo = findViewById(R.id.update_info);
        bannerText = findViewById(R.id.update_banner_text);
        btnConnect = findViewById(R.id.btn_connect);
        btnBack = findViewById(R.id.btn_back);
        btnReset = findViewById(R.id.btn_reset);
        btnUpdate = findViewById(R.id.btn_update);
        btnRetry = findViewById(R.id.btn_retry);
        btnBannerUpdate = findViewById(R.id.btn_banner_update);
        btnBannerClose = findViewById(R.id.btn_banner_close);

        errorWrap = findViewById(R.id.error_wrap);
        errorText = findViewById(R.id.error_text);
        btnRetry.setOnClickListener(v -> { hideError(); loadStorefront(); });

        configureWebView();
        updateMeta();
        resetUpdateState();
        hideBanner();

        btnConnect.setOnClickListener(v -> connect());
        btnBack.setOnClickListener(v -> loadStorefront());
        btnReset.setOnClickListener(v -> clearSavedServer());
        btnUpdate.setOnClickListener(v -> openExternal(latestUpdateUrl));
        btnBannerUpdate.setOnClickListener(v -> openExternal(latestUpdateUrl));
        btnBannerClose.setOnClickListener(v -> hideBanner());

        // Долгое нажатие на WebView — экран настроек подключения (как у «Склада»).
        webView.setOnLongClickListener(v -> { showSetup("", false); return true; });

        String saved = prefs.getString(KEY_URL, "");
        if (saved.isEmpty() && BuildConfig.SHOP_URL != null && !BuildConfig.SHOP_URL.isEmpty()) {
            saved = BuildConfig.SHOP_URL;
        }
        if (!saved.isEmpty()) {
            setServerUrl(saved, false);
        }

        if (!applyIncomingIntent(getIntent())) {
            if (!baseUrl.isEmpty()) {
                loadStorefront();
            } else {
                showSetup("Укажите адрес витрины вашего магазина или откройте ссылку shop://connect?url=…", false);
            }
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (applyIncomingIntent(intent)) return;
        updateMeta();
    }

    private void connect() {
        String raw = urlInput.getText().toString().trim();
        if (raw.isEmpty()) {
            showSetup("Введите адрес магазина, например https://myshop.ru/", true);
            return;
        }
        setServerUrl(raw, true);
        loadStorefront();
    }

    private void clearSavedServer() {
        baseUrl = "";
        latestUpdateUrl = "";
        prefs.edit().remove(KEY_URL).apply();
        urlInput.setText("");
        webView.loadUrl("about:blank");
        updateMeta();
        resetUpdateState();
        hideBanner();
        showSetup("Адрес магазина сброшен. Укажите новый адрес или откройте ссылку подключения.", false);
    }

    private void setServerUrl(String raw, boolean showToast) {
        String url = normalize(raw);
        baseUrl = url;
        urlInput.setText(url);
        prefs.edit().putString(KEY_URL, url).apply();
        updateMeta();
        checkForUpdates();
        if (showToast) {
            Toast.makeText(this, "Магазин сохранён", Toast.LENGTH_SHORT).show();
        }
    }

    /** Добавляет https:// и ведёт на корень витрины, если путь не указан. */
    private String normalize(String raw) {
        String s = raw == null ? "" : raw.trim();
        if (s.isEmpty()) return "";
        if (!s.startsWith("http://") && !s.startsWith("https://")) s = "https://" + s;
        try {
            Uri u = Uri.parse(s);
            String scheme = u.getScheme() == null ? "https" : u.getScheme();
            String host = u.getHost();
            if (host == null || host.isEmpty()) return s;
            int port = u.getPort();
            String path = u.getPath() == null ? "" : u.getPath().trim();
            String query = u.getQuery();
            String fragment = u.getFragment();
            if (path.isEmpty()) {
                path = "/";
            }
            Uri.Builder b = new Uri.Builder().scheme(scheme).encodedAuthority(host + (port != -1 ? ":" + port : "")).encodedPath(path);
            if (!TextUtils.isEmpty(query)) b.encodedQuery(query);
            if (!TextUtils.isEmpty(fragment)) b.encodedFragment(fragment);
            return b.build().toString();
        } catch (Exception ignored) {
            return s;
        }
    }

    private void loadStorefront() {
        if (baseUrl == null || baseUrl.isEmpty()) {
            showSetup("Сначала укажите адрес витрины в настройках подключения.", true);
            return;
        }
        setupView.setVisibility(View.GONE);
        mainView.setVisibility(View.VISIBLE);
        webView.loadUrl(baseUrl);
    }

    /** Ссылки только своего магазина открываются внутри приложения, внешние — в браузере. */
    private boolean isInternalUrl(String url) {
        if (baseUrl == null || baseUrl.isEmpty() || url == null || url.isEmpty()) return false;
        try {
            Uri current = Uri.parse(baseUrl);
            Uri target = Uri.parse(url);
            String curHost = current.getHost();
            String tgtHost = target.getHost();
            if (curHost == null || tgtHost == null) return url.startsWith(baseUrl);
            String curScheme = current.getScheme() == null ? "https" : current.getScheme();
            String tgtScheme = target.getScheme() == null ? "https" : target.getScheme();
            int curPort = current.getPort() != -1 ? current.getPort() : ("https".equalsIgnoreCase(curScheme) ? 443 : 80);
            int tgtPort = target.getPort() != -1 ? target.getPort() : ("https".equalsIgnoreCase(tgtScheme) ? 443 : 80);
            return curScheme.equalsIgnoreCase(tgtScheme)
                    && curHost.equalsIgnoreCase(tgtHost)
                    && curPort == tgtPort;
        } catch (Exception ignored) {
            return false;
        }
    }

    private boolean applyIncomingIntent(Intent intent) {
        if (intent == null) return false;
        Uri data = intent.getData();
        if (data == null) return false;
        String scheme = data.getScheme() == null ? "" : data.getScheme().toLowerCase();
        if (!"shop".equals(scheme)) return false;
        String host = data.getHost() == null ? "" : data.getHost().toLowerCase();

        if ("install".equals(host)) {
            String origin = getOriginBase();
            if (TextUtils.isEmpty(origin)) {
                showSetup("Сначала подключитесь к магазину — затем ссылка shop://install откроет страницу обновлений.", false);
            } else {
                openExternal(origin + "/download/app");
            }
            return true;
        }

        String urlParam = data.getQueryParameter("url");
        if (TextUtils.isEmpty(urlParam)) urlParam = data.getQueryParameter("server");
        if (TextUtils.isEmpty(urlParam)) return false;

        setServerUrl(urlParam, false);
        if ("connect".equals(host) || "open".equals(host) || "1".equals(data.getQueryParameter("autoconnect"))) {
            Toast.makeText(this, "Магазин импортирован из ссылки", Toast.LENGTH_SHORT).show();
            loadStorefront();
        } else {
            showSetup("Адрес получен из ссылки. Нажмите «Сохранить и открыть магазин».", false);
        }
        return true;
    }

    private void updateMeta() {
        String current = (baseUrl == null || baseUrl.isEmpty()) ? "не подключён" : baseUrl;
        appMeta.setText("Версия " + BuildConfig.VERSION_NAME + " • package " + BuildConfig.APPLICATION_ID + "\nТекущий магазин: " + current);
        setupHint.setText("Подключение хранится в настройках APK. Deep links: shop://setup?url=https://ваш-домен/ — настройка,\nshop://connect?url=https://ваш-домен/ — мгновенное подключение,\nshop://install — страница скачивания APK. QR-коды генерируются на странице /download/app.");
        btnBack.setVisibility(baseUrl == null || baseUrl.isEmpty() ? View.GONE : View.VISIBLE);
        btnReset.setVisibility(baseUrl == null || baseUrl.isEmpty() ? View.GONE : View.VISIBLE);
    }

    private void resetUpdateState() {
        latestUpdateUrl = "";
        updateInfo.setText("Проверка станет доступна после подключения к магазину.");
        btnUpdate.setVisibility(View.GONE);
    }

    private void hideBanner() {
        if (updateBanner != null) updateBanner.setVisibility(View.GONE);
    }

    private void showBanner(String message, String downloadUrl) {
        latestUpdateUrl = downloadUrl == null ? "" : downloadUrl;
        bannerText.setText(message);
        updateBanner.setVisibility(TextUtils.isEmpty(latestUpdateUrl) ? View.GONE : View.VISIBLE);
    }

    private String getOriginBase() {
        if (TextUtils.isEmpty(baseUrl)) return "";
        try {
            Uri u = Uri.parse(baseUrl);
            String scheme = u.getScheme() == null ? "https" : u.getScheme();
            String authority = u.getEncodedAuthority();
            if (TextUtils.isEmpty(authority)) return "";
            return new Uri.Builder().scheme(scheme).encodedAuthority(authority).build().toString();
        } catch (Exception ignored) {
            return "";
        }
    }

    private int compareVersions(String left, String right) {
        String[] a = (left == null ? "" : left).split("\\.");
        String[] b = (right == null ? "" : right).split("\\.");
        int size = Math.max(a.length, b.length);
        for (int i = 0; i < size; i++) {
            int av = i < a.length ? parseIntSafe(a[i]) : 0;
            int bv = i < b.length ? parseIntSafe(b[i]) : 0;
            if (av != bv) return av > bv ? 1 : -1;
        }
        return 0;
    }

    private int parseIntSafe(String value) {
        try {
            return Integer.parseInt(value.replaceAll("[^0-9]", ""));
        } catch (Exception ignored) {
            return 0;
        }
    }

    private String readAll(InputStream stream) throws Exception {
        BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) sb.append(line);
        reader.close();
        return sb.toString();
    }

    /** Блок 25: проверка обновлений покупательского APK через /api/app/version. */
    private void checkForUpdates() {
        if (TextUtils.isEmpty(baseUrl)) {
            resetUpdateState();
            return;
        }
        final String origin = getOriginBase();
        if (TextUtils.isEmpty(origin)) {
            applyUpdateState("Не удалось определить адрес магазина для проверки обновлений.", "", false);
            return;
        }
        updateInfo.setText("Проверяем наличие обновлений…");
        btnUpdate.setVisibility(View.GONE);
        new Thread(() -> {
            HttpURLConnection conn = null;
            try {
                String apiUrl = origin + "/api/app/version";
                conn = (HttpURLConnection) new URL(apiUrl).openConnection();
                conn.setConnectTimeout(7000);
                conn.setReadTimeout(7000);
                conn.setRequestMethod("GET");
                conn.setRequestProperty("Accept", "application/json");
                int code = conn.getResponseCode();
                InputStream stream = code >= 200 && code < 400 ? conn.getInputStream() : conn.getErrorStream();
                String body = stream == null ? "" : readAll(stream);
                if (code < 200 || code >= 400) {
                    throw new IllegalStateException("HTTP " + code);
                }
                JSONObject root = new JSONObject(body);
                String latestVersion = root.optString("version", "");
                String downloadUrl = root.optString("download_url", "");
                String updatedAt = root.optString("updated_at", "");
                boolean hasUpdate = compareVersions(latestVersion, BuildConfig.VERSION_NAME) > 0;
                String message;
                if (hasUpdate) {
                    message = "Доступна версия " + latestVersion + (TextUtils.isEmpty(updatedAt) ? "" : " · обновлено " + updatedAt);
                } else {
                    message = "Установлена актуальная версия " + BuildConfig.VERSION_NAME + (TextUtils.isEmpty(updatedAt) ? "" : " · сервер проверен " + updatedAt);
                }
                final boolean fHasUpdate = hasUpdate;
                final String fMessage = message;
                final String fUrl = downloadUrl;
                runOnUiThread(() -> {
                    applyUpdateState(fMessage, fHasUpdate ? fUrl : "", fHasUpdate);
                    if (fHasUpdate && !TextUtils.isEmpty(fUrl)) {
                        showBanner("Доступна новая версия приложения " + latestVersion, fUrl);
                    }
                });
            } catch (Exception e) {
                String message = e.getMessage();
                final String fMessage = "Не удалось проверить обновления: " + (message == null ? "ошибка сети" : message);
                runOnUiThread(() -> applyUpdateState(fMessage, "", false));
            } finally {
                if (conn != null) conn.disconnect();
            }
        }).start();
    }

    private void applyUpdateState(String message, String downloadUrl, boolean hasUpdate) {
        latestUpdateUrl = hasUpdate ? downloadUrl : "";
        updateInfo.setText(message);
        btnUpdate.setVisibility(hasUpdate && !TextUtils.isEmpty(downloadUrl) ? View.VISIBLE : View.GONE);
    }

    private void openExternal(String url) {
        if (TextUtils.isEmpty(url)) {
            Toast.makeText(this, "Ссылка пока недоступна", Toast.LENGTH_SHORT).show();
            return;
        }
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "Не удалось открыть ссылку", Toast.LENGTH_SHORT).show();
        }
    }

    private void showError(String message) {
        if (errorWrap == null) return;
        errorText.setText(message);
        errorWrap.setVisibility(View.VISIBLE);
    }

    private void hideError() {
        if (errorWrap == null) return;
        errorWrap.setVisibility(View.GONE);
    }

    private void showSetup(String message, boolean isError) {
        mainView.setVisibility(View.GONE);
        setupView.setVisibility(View.VISIBLE);
        if (TextUtils.isEmpty(message)) {
            setupError.setVisibility(View.GONE);
            setupError.setText("");
        } else {
            setupError.setVisibility(View.VISIBLE);
            setupError.setText(message);
            setupError.setTextColor(Color.parseColor(isError ? "#DC2626" : "#4338CA"));
        }
        updateMeta();
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void configureWebView() {
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setUserAgentString(s.getUserAgentString() + APP_UA);
        CookieManager.getInstance().setAcceptCookie(true);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            CookieManager.getInstance().setAcceptThirdPartyCookies(webView, false);
        }

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                if (url == null) return false;
                Uri u = Uri.parse(url);
                String scheme = u.getScheme() == null ? "" : u.getScheme().toLowerCase();
                if ("http".equals(scheme) || "https".equals(scheme)) {
                    if (isInternalUrl(url)) return false; // остаёмся в приложении
                    openExternal(url);                    // внешнее — в браузер
                    return true;
                }
                openExternal(url);
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request != null && request.isForMainFrame()) {
                    showError("Магазин недоступен. Проверьте интернет и повторите.");
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (filePathCallback != null) {
                    filePathCallback.onReceiveValue(null);
                }
                filePathCallback = callback;
                try {
                    Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
                    intent.addCategory(Intent.CATEGORY_OPENABLE);
                    intent.setType("image/*");
                    intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, false);
                    startActivityForResult(Intent.createChooser(intent, "Выберите изображение"), REQ_FILE);
                } catch (ActivityNotFoundException e) {
                    filePathCallback = null;
                    Toast.makeText(MainActivity.this, "Нет приложения для выбора файла", Toast.LENGTH_SHORT).show();
                    return false;
                }
                return true;
            }
        });

        webView.setDownloadListener((url, userAgent, contentDisposition, mimetype, contentLength) ->
                openExternal(url));
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQ_FILE) {
            Uri[] out = null;
            if (resultCode == Activity.RESULT_OK && data != null && data.getData() != null) {
                out = new Uri[]{data.getData()};
            }
            if (filePathCallback != null) {
                filePathCallback.onReceiveValue(out);
                filePathCallback = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    protected void onSaveInstanceState(@NonNull Bundle outState) {
        super.onSaveInstanceState(outState);
        webView.saveState(outState);
    }

    @Override
    public void onBackPressed() {
        if (setupView.getVisibility() == View.VISIBLE) {
            if (!baseUrl.isEmpty()) {
                loadStorefront();
                return;
            }
        }
        if (webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }
}
