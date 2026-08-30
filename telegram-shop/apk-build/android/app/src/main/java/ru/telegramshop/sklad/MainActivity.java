package ru.telegramshop.sklad;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
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
import android.widget.TextView;
import android.widget.Toast;

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
 * «Склад» — WebView-обёртка PWA /warehouse/.
 * Поддерживает:
 * - ввод адреса сервера при первом запуске,
 * - импорт адреса через deep link: sklad://setup?url=https://site/warehouse/
 * - мгновенное подключение через deep link: sklad://connect?url=https://site/warehouse/
 * - множественный выбор фото,
 * - экран «О приложении»/настройки по долгому нажатию,
 * - проверку новых APK-релизов на подключённом сервере.
 */
public class MainActivity extends AppCompatActivity {

    private static final String PREFS = "sklad_prefs";
    private static final String KEY_URL = "server_url";
    private static final int REQ_FILE = 1001;
    private static final String APP_UA = " SkladApp/1.0.3";

    private WebView webView;
    private View mainView, setupView;
    private EditText urlInput;
    private TextView setupError, appMeta, setupHint, updateInfo;
    private Button btnConnect, btnBack, btnReset, btnUpdate;
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
        urlInput = findViewById(R.id.url_input);
        setupError = findViewById(R.id.setup_error);
        setupHint = findViewById(R.id.setup_hint);
        appMeta = findViewById(R.id.app_meta);
        updateInfo = findViewById(R.id.update_info);
        btnConnect = findViewById(R.id.btn_connect);
        btnBack = findViewById(R.id.btn_back);
        btnReset = findViewById(R.id.btn_reset);
        btnUpdate = findViewById(R.id.btn_update);

        configureWebView();
        updateMeta();
        resetUpdateState();

        btnConnect.setOnClickListener(v -> connect());
        btnBack.setOnClickListener(v -> loadWarehouse());
        btnReset.setOnClickListener(v -> clearSavedServer());
        btnUpdate.setOnClickListener(v -> openExternal(latestUpdateUrl));

        String saved = prefs.getString(KEY_URL, "");
        if (saved.isEmpty() && BuildConfig.WAREHOUSE_URL != null && !BuildConfig.WAREHOUSE_URL.isEmpty()) {
            saved = BuildConfig.WAREHOUSE_URL;
        }
        if (!saved.isEmpty()) {
            setServerUrl(saved, false);
        }

        if (!applyIncomingIntent(getIntent())) {
            if (!baseUrl.isEmpty()) {
                loadWarehouse();
            } else {
                showSetup("Введите адрес вашего сервера.");
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
            setupError.setText("Введите адрес сервера, например https://myshop.ru/warehouse/");
            setupError.setVisibility(View.VISIBLE);
            return;
        }
        setServerUrl(raw, true);
        loadWarehouse();
    }

    private void clearSavedServer() {
        baseUrl = "";
        latestUpdateUrl = "";
        prefs.edit().remove(KEY_URL).apply();
        urlInput.setText("");
        webView.loadUrl("about:blank");
        updateMeta();
        resetUpdateState();
        showSetup("Адрес сервера сброшен. Введите новый адрес или откройте ссылку настройки.");
    }

    private void setServerUrl(String raw, boolean showToast) {
        String url = normalize(raw);
        baseUrl = url;
        urlInput.setText(url);
        prefs.edit().putString(KEY_URL, url).apply();
        updateMeta();
        checkForUpdates();
        if (showToast) {
            Toast.makeText(this, "Сервер сохранён", Toast.LENGTH_SHORT).show();
        }
    }

    /** Добавляет https:// и путь /warehouse/, если путь не указан. */
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
            if (path.isEmpty() || "/".equals(path)) {
                path = "/warehouse/";
            } else if ("/warehouse".equals(path)) {
                path = "/warehouse/";
            } else if (!path.startsWith("/warehouse/")) {
                path = path.replaceAll("/+$", "") + "/warehouse/";
            }
            Uri.Builder b = new Uri.Builder().scheme(scheme).encodedAuthority(host + (port != -1 ? ":" + port : "")).encodedPath(path);
            if (!TextUtils.isEmpty(query)) b.encodedQuery(query);
            if (!TextUtils.isEmpty(fragment)) b.encodedFragment(fragment);
            return b.build().toString();
        } catch (Exception ignored) {
            return s;
        }
    }

    private void loadWarehouse() {
        if (baseUrl == null || baseUrl.isEmpty()) {
            showSetup("Сначала укажите адрес сервера.");
            return;
        }
        setupView.setVisibility(View.GONE);
        mainView.setVisibility(View.VISIBLE);
        webView.loadUrl(baseUrl);
    }

    private boolean isInternalUrl(String url) {
        if (baseUrl == null || baseUrl.isEmpty() || url == null || url.isEmpty()) return false;
        try {
            Uri current = Uri.parse(baseUrl);
            Uri target = Uri.parse(url);
            String curScheme = current.getScheme() == null ? "" : current.getScheme();
            String tgtScheme = target.getScheme() == null ? "" : target.getScheme();
            String curHost = current.getHost();
            String tgtHost = target.getHost();
            if (curHost == null || tgtHost == null) return url.startsWith(baseUrl);
            int curPort = current.getPort() != -1 ? current.getPort() : ("https".equalsIgnoreCase(curScheme) ? 443 : 80);
            int tgtPort = target.getPort() != -1 ? target.getPort() : ("https".equalsIgnoreCase(tgtScheme) ? 443 : 80);
            String path = target.getPath() == null ? "/" : target.getPath();
            boolean sameOrigin = curScheme.equalsIgnoreCase(tgtScheme)
                    && curHost.equalsIgnoreCase(tgtHost)
                    && curPort == tgtPort;
            return sameOrigin && (path.equals("/warehouse") || path.startsWith("/warehouse/") || url.startsWith(baseUrl));
        } catch (Exception ignored) {
            return url.startsWith(baseUrl);
        }
    }

    private boolean applyIncomingIntent(Intent intent) {
        if (intent == null) return false;
        Uri data = intent.getData();
        if (data == null) return false;
        String scheme = data.getScheme() == null ? "" : data.getScheme().toLowerCase();
        String host = data.getHost() == null ? "" : data.getHost().toLowerCase();
        String urlParam = data.getQueryParameter("url");
        if (TextUtils.isEmpty(urlParam)) urlParam = data.getQueryParameter("server");
        if (TextUtils.isEmpty(urlParam) && ("http".equals(scheme) || "https".equals(scheme))) {
            urlParam = data.getQueryParameter("sklad_url");
        }
        if (TextUtils.isEmpty(urlParam) && "1".equals(data.getQueryParameter("reset"))) {
            clearSavedServer();
            return true;
        }
        if (TextUtils.isEmpty(urlParam)) return false;

        setServerUrl(urlParam, false);
        String message = "Адрес получен из ссылки настройки. Нажмите «Подключиться» или откройте склад.";
        if ("connect".equals(host) || "open".equals(host) || "1".equals(data.getQueryParameter("autoconnect"))) {
            Toast.makeText(this, "Сервер импортирован из ссылки", Toast.LENGTH_SHORT).show();
            loadWarehouse();
        } else {
            showSetup(message);
        }
        return true;
    }

    private void updateMeta() {
        String current = (baseUrl == null || baseUrl.isEmpty()) ? "не подключён" : baseUrl;
        appMeta.setText("Версия " + BuildConfig.VERSION_NAME + " • package " + BuildConfig.APPLICATION_ID + "\nТекущий сервер: " + current);
        setupHint.setText("Можно открыть ссылку вида sklad://setup?url=https://ваш-домен/warehouse/\nили sklad://connect?url=https://ваш-домен/warehouse/ для мгновенного подключения. QR-код генерируется на странице /download/android.");
        btnBack.setVisibility(baseUrl == null || baseUrl.isEmpty() ? View.GONE : View.VISIBLE);
        btnReset.setVisibility(baseUrl == null || baseUrl.isEmpty() ? View.GONE : View.VISIBLE);
    }

    private void resetUpdateState() {
        latestUpdateUrl = "";
        updateInfo.setText("Проверка станет доступна после подключения к серверу.");
        btnUpdate.setVisibility(View.GONE);
    }

    private void applyUpdateState(String message, String downloadUrl, boolean hasUpdate) {
        latestUpdateUrl = hasUpdate ? downloadUrl : "";
        updateInfo.setText(message);
        btnUpdate.setVisibility(hasUpdate && !TextUtils.isEmpty(downloadUrl) ? View.VISIBLE : View.GONE);
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

    private void checkForUpdates() {
        if (TextUtils.isEmpty(baseUrl)) {
            resetUpdateState();
            return;
        }
        final String origin = getOriginBase();
        if (TextUtils.isEmpty(origin)) {
            applyUpdateState("Не удалось определить origin сервера для проверки обновлений.", "", false);
            return;
        }
        updateInfo.setText("Проверяем наличие обновлений APK…");
        btnUpdate.setVisibility(View.GONE);
        final String currentServer = baseUrl;
        new Thread(() -> {
            HttpURLConnection conn = null;
            try {
                String apiUrl = origin + "/api/releases/android?server=" + URLEncoder.encode(currentServer, "UTF-8");
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
                JSONObject apk = root.optJSONObject("apk");
                if (apk == null) {
                    runOnUiThread(() -> applyUpdateState("На сервере пока нет APK-релиза для проверки обновлений.", "", false));
                    return;
                }
                String latestVersion = apk.optString("version", "");
                String downloadUrl = apk.optString("download_url", "");
                String updatedAt = apk.optString("updated_at", "");
                boolean hasUpdate = compareVersions(latestVersion, BuildConfig.VERSION_NAME) > 0;
                String message;
                if (hasUpdate) {
                    message = "Доступна версия " + latestVersion + (TextUtils.isEmpty(updatedAt) ? "" : " · обновлено " + updatedAt);
                } else {
                    message = "Установлена актуальная версия " + BuildConfig.VERSION_NAME + (TextUtils.isEmpty(updatedAt) ? "" : " · сервер проверен " + updatedAt);
                }
                runOnUiThread(() -> applyUpdateState(message, downloadUrl, hasUpdate));
            } catch (Exception e) {
                String message = e.getMessage();
                runOnUiThread(() -> applyUpdateState("Не удалось проверить обновления: " + (message == null ? "ошибка сети" : message), "", false));
            } finally {
                if (conn != null) conn.disconnect();
            }
        }).start();
    }

    private void openExternal(String url) {
        if (TextUtils.isEmpty(url)) {
            Toast.makeText(this, "Ссылка обновления пока недоступна", Toast.LENGTH_SHORT).show();
            return;
        }
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "Не удалось открыть ссылку", Toast.LENGTH_SHORT).show();
        }
    }

    private void showSetup(String error) {
        mainView.setVisibility(View.GONE);
        setupView.setVisibility(View.VISIBLE);
        setupError.setVisibility(error == null ? View.GONE : View.VISIBLE);
        if (error != null) setupError.setText(error);
        updateMeta();
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void configureWebView() {
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setSupportZoom(true);
        s.setBuiltInZoomControls(true);
        s.setDisplayZoomControls(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        s.setUserAgentString(s.getUserAgentString() + APP_UA);
        CookieManager cm = CookieManager.getInstance();
        cm.setAcceptCookie(true);
        cm.setAcceptThirdPartyCookies(webView, true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String url = uri.toString();
                if (isInternalUrl(url)) return false;
                if (url.startsWith("sklad://")) {
                    Intent i = new Intent(Intent.ACTION_VIEW, uri, MainActivity.this, MainActivity.class);
                    startActivity(i);
                    return true;
                }
                if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("tg://")) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, uri));
                    } catch (ActivityNotFoundException ignored) { }
                    return true;
                }
                return false;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    Toast.makeText(MainActivity.this,
                            "Сервер недоступен: " + error.getDescription(),
                            Toast.LENGTH_LONG).show();
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                if (filePathCallback != null) filePathCallback.onReceiveValue(null);
                filePathCallback = callback;
                try {
                    Intent i = params.createIntent();
                    i.addCategory(Intent.CATEGORY_OPENABLE);
                    i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                    startActivityForResult(i, REQ_FILE);
                } catch (Exception e) {
                    filePathCallback = null;
                    return false;
                }
                return true;
            }
        });

        webView.setOnLongClickListener(v -> {
            showSetup("Настройки приложения. Можно сменить сервер, открыть ссылку настройки, проверить обновления или сбросить сохранённый адрес.");
            return true;
        });
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_FILE) {
            if (filePathCallback == null) return;
            Uri[] results = null;
            if (resultCode == Activity.RESULT_OK && data != null) {
                if (data.getClipData() != null) {
                    int count = data.getClipData().getItemCount();
                    results = new Uri[count];
                    for (int i = 0; i < count; i++) {
                        results[i] = data.getClipData().getItemAt(i).getUri();
                    }
                } else if (data.getData() != null) {
                    results = new Uri[]{data.getData()};
                }
            }
            filePathCallback.onReceiveValue(results);
            filePathCallback = null;
        }
    }

    @Override
    public void onBackPressed() {
        if (setupView.getVisibility() == View.VISIBLE) {
            if (!baseUrl.isEmpty()) {
                loadWarehouse();
                return;
            }
        }
        if (webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }
}
