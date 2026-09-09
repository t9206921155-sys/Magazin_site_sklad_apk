package ru.telegramshop.sklad;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Intent;
import android.graphics.Color;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.provider.MediaStore;
import android.text.TextUtils;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
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

import androidx.activity.result.ActivityResultLauncher;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;

import com.journeyapps.barcodescanner.ScanContract;
import com.journeyapps.barcodescanner.ScanIntentResult;
import com.journeyapps.barcodescanner.ScanOptions;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

/**
 * «Склад» — WebView-обёртка PWA /warehouse/.
 * Поддерживает:
 * - ввод адреса сервера при первом запуске,
 * - импорт адреса через deep link: sklad://setup?url=https://site/warehouse/
 * - мгновенное подключение через deep link: sklad://connect?url=https://site/warehouse/
 * - множественный выбор фото,
 * - доступ WebView к камере для сканирования QR/штрих-кодов внутри APK,
 * - нативный fallback-сканер Android через bridge, если BarcodeDetector нестабилен,
 * - экран «О приложении»/настройки по долгому нажатию,
 * - проверку новых APK-релизов на подключённом сервере.
 */
public class MainActivity extends AppCompatActivity {

    private static final String PREFS = "sklad_prefs";
    private static final String KEY_URL = "server_url";
    private static final int REQ_FILE = 1001;
    private static final int REQ_CAMERA_WEB = 1002;
    private static final int REQ_CAMERA_NATIVE = 1003;
    private static final String APP_UA = " SkladApp/1.1.0";

    private WebView webView;
    private View mainView, setupView;
    private EditText urlInput;
    private TextView setupError, appMeta, setupHint, updateInfo;
    private Button btnConnect, btnBack, btnReset, btnUpdate;
    private SharedPreferences prefs;
    private String baseUrl = "";
    private String latestUpdateUrl = "";
    private String pendingNativeScanMode = "";
    private String activeNativeScanMode = "";
    private ValueCallback<Uri[]> filePathCallback;
    private PermissionRequest pendingCameraPermissionRequest;
    private ActivityResultLauncher<ScanOptions> nativeScanLauncher;
    private View errorWrap;
    private TextView errorText;
    private Button btnRetry;

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

        nativeScanLauncher = registerForActivityResult(new ScanContract(), this::handleNativeScanResult);

        errorWrap = findViewById(R.id.error_wrap);
        errorText = findViewById(R.id.error_text);
        btnRetry = findViewById(R.id.btn_retry);
        btnRetry.setOnClickListener(v -> { hideError(); loadWarehouse(); });

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
                showSetup("Откройте настройки подключения и укажите адрес вашего склада на VPS.", false);
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
            showSetup("Введите адрес сервера, например https://myshop.ru/warehouse/", true);
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
        showSetup("Адрес склада сброшен. Укажите новый адрес в настройках подключения или откройте ссылку настройки.", false);
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
            showSetup("Сначала укажите адрес склада в настройках подключения.", true);
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
        // Блок 25: приём отсканированного кода от ТСД/терминала сбора данных.
        // Настраивается в ТСД как intent/URL: sklad://scan?code=4600000000&mode=search
        if (("scan".equals(host) || "code".equals(host)) && !TextUtils.isEmpty(data.getQueryParameter("code"))) {
            String code = data.getQueryParameter("code");
            String mode = data.getQueryParameter("mode");
            if (TextUtils.isEmpty(baseUrl)) {
                Toast.makeText(this, "Сначала подключитесь к серверу склада", Toast.LENGTH_LONG).show();
                return true;
            }
            if (mainView.getVisibility() != View.VISIBLE) loadWarehouse();
            vibrateFeedback();
            final String fCode = code;
            final String fMode = sanitizeScanMode(mode);
            webView.postDelayed(() -> dispatchNativeScanResult(fCode, fMode), 600);
            Toast.makeText(this, "Код получен от сканера", Toast.LENGTH_SHORT).show();
            return true;
        }
        if (TextUtils.isEmpty(urlParam)) return false;

        setServerUrl(urlParam, false);
        String message = "Адрес получен из ссылки настройки. Нажмите «Подключиться» или откройте склад.";
        if ("connect".equals(host) || "open".equals(host) || "1".equals(data.getQueryParameter("autoconnect"))) {
            Toast.makeText(this, "Сервер импортирован из ссылки", Toast.LENGTH_SHORT).show();
            loadWarehouse();
        } else {
            showSetup(message, false);
        }
        return true;
    }

    private void updateMeta() {
        String current = (baseUrl == null || baseUrl.isEmpty()) ? "не подключён" : baseUrl;
        appMeta.setText("Версия " + BuildConfig.VERSION_NAME + " • package " + BuildConfig.APPLICATION_ID + "\nТекущий сервер: " + current);
        setupHint.setText("Подключение к складу хранится в настройках APK. Можно открыть ссылку вида sklad://setup?url=https://ваш-домен/warehouse/\nили sklad://connect?url=https://ваш-домен/warehouse/ для мгновенного подключения. QR-код генерируется на странице /download/android, а внутри APK есть web-сканер и нативный fallback-сканер Android.");
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

    private boolean isCurrentInternalPage() {
        String currentUrl = webView == null ? "" : webView.getUrl();
        return currentUrl != null && !currentUrl.isEmpty() && isInternalUrl(currentUrl);
    }

    private String sanitizeScanMode(String mode) {
        if ("receive".equals(mode) || "sell".equals(mode) || "inventory".equals(mode)) return mode;
        return "search";
    }

    private String nativePromptForMode(String mode) {
        switch (sanitizeScanMode(mode)) {
            case "receive":
                return "Сканируйте код для приёмки";
            case "sell":
                return "Сканируйте код для продажи";
            case "inventory":
                return "Сканируйте код для инвентаризации";
            default:
                return "Сканируйте QR или штрих-код";
        }
    }

    private void startNativeScan(String mode) {
        if (!isCurrentInternalPage()) {
            Toast.makeText(this, "Нативный сканер доступен только внутри /warehouse/", Toast.LENGTH_SHORT).show();
            return;
        }
        String safeMode = sanitizeScanMode(mode);
        if (!hasCameraPermission()) {
            pendingNativeScanMode = safeMode;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                requestPermissions(new String[]{Manifest.permission.CAMERA}, REQ_CAMERA_NATIVE);
            }
            return;
        }
        launchNativeScanner(safeMode);
    }

    private void launchNativeScanner(String mode) {
        activeNativeScanMode = sanitizeScanMode(mode);
        ScanOptions options = new ScanOptions();
        options.setDesiredBarcodeFormats(ScanOptions.ALL_CODE_TYPES);
        options.setPrompt(nativePromptForMode(activeNativeScanMode));
        options.setBeepEnabled(false);
        options.setOrientationLocked(false);
        options.setBarcodeImageEnabled(false);
        nativeScanLauncher.launch(options);
    }

    private void handleNativeScanResult(ScanIntentResult result) {
        if (result == null || result.getContents() == null) {
            activeNativeScanMode = "";
            dispatchNativeScanCancelled();
            return;
        }
        vibrateFeedback();
        dispatchNativeScanResult(result.getContents(), activeNativeScanMode);
        activeNativeScanMode = "";
    }

    /** Блок 25: короткая вибрация — тактильный фидбек успешного сканирования. */
    private void vibrateFeedback() {
        try {
            Vibrator v = (Vibrator) getSystemService(VIBRATOR_SERVICE);
            if (v == null) return;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                v.vibrate(VibrationEffect.createOneShot(60, VibrationEffect.DEFAULT_AMPLITUDE));
            } else {
                v.vibrate(60);
            }
        } catch (Exception ignored) { }
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

    private void dispatchNativeScanResult(String value, String mode) {
        if (!isCurrentInternalPage()) return;
        String js = "window.__nativeScanResult && window.__nativeScanResult("
                + JSONObject.quote(value == null ? "" : value) + ","
                + JSONObject.quote(sanitizeScanMode(mode)) + ");";
        webView.evaluateJavascript(js, null);
    }

    private void dispatchNativeScanCancelled() {
        if (!isCurrentInternalPage()) return;
        webView.evaluateJavascript("window.__nativeScanCancelled && window.__nativeScanCancelled();", null);
    }

    private boolean hasCameraPermission() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.M
                || ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED;
    }

    private boolean isTrustedOrigin(Uri origin) {
        if (origin == null) return false;
        if (TextUtils.isEmpty(baseUrl)) return false;
        try {
            Uri current = Uri.parse(baseUrl);
            String currentScheme = current.getScheme() == null ? "" : current.getScheme();
            String originScheme = origin.getScheme() == null ? "" : origin.getScheme();
            String currentHost = current.getHost();
            String originHost = origin.getHost();
            if (currentHost == null || originHost == null) return false;
            int currentPort = current.getPort() != -1 ? current.getPort() : ("https".equalsIgnoreCase(currentScheme) ? 443 : 80);
            int originPort = origin.getPort() != -1 ? origin.getPort() : ("https".equalsIgnoreCase(originScheme) ? 443 : 80);
            return currentScheme.equalsIgnoreCase(originScheme)
                    && currentHost.equalsIgnoreCase(originHost)
                    && currentPort == originPort;
        } catch (Exception ignored) {
            return false;
        }
    }

    private boolean wantsVideoCapture(PermissionRequest request) {
        if (request == null) return false;
        for (String resource : request.getResources()) {
            if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(resource)) {
                return true;
            }
        }
        return false;
    }

    private void handleWebPermissionRequest(PermissionRequest request) {
        if (request == null) return;
        if (!wantsVideoCapture(request) || !isTrustedOrigin(request.getOrigin())) {
            request.deny();
            return;
        }
        if (hasCameraPermission()) {
            request.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE});
            return;
        }
        pendingCameraPermissionRequest = request;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            requestPermissions(new String[]{Manifest.permission.CAMERA}, REQ_CAMERA_WEB);
        } else {
            request.deny();
        }
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
            setupError.setTextColor(Color.parseColor(isError ? "#DC2626" : "#0F766E"));
        }
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
        webView.addJavascriptInterface(new AndroidScannerBridge(), "AndroidScanner");
        webView.addJavascriptInterface(new NativeBridge(), "AndroidNative");

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
                    showError("Сервер склада недоступен (" + error.getDescription()
                            + ").\nПроверьте интернет и адрес сервера, затем нажмите «Повторить».");
                }
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (!TextUtils.isEmpty(url) && !"about:blank".equals(url) && isInternalUrl(url)) {
                    hideError();
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(() -> handleWebPermissionRequest(request));
            }

            @Override
            public void onPermissionRequestCanceled(PermissionRequest request) {
                if (pendingCameraPermissionRequest == request) {
                    pendingCameraPermissionRequest = null;
                }
            }


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
            showSetup("Настройки подключения APK. Здесь можно изменить адрес склада, проверить обновления и при необходимости сбросить подключение.", false);
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
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        boolean granted = grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED;
        if (requestCode == REQ_CAMERA_WEB) {
            PermissionRequest request = pendingCameraPermissionRequest;
            pendingCameraPermissionRequest = null;
            if (request == null) return;
            if (granted) {
                request.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE});
                Toast.makeText(this, "Камера разрешена — можно сканировать штрих-коды и QR", Toast.LENGTH_SHORT).show();
            } else {
                request.deny();
                Toast.makeText(this, "Без доступа к камере сканер в приложении не запустится", Toast.LENGTH_LONG).show();
            }
            return;
        }
        if (requestCode == REQ_CAMERA_NATIVE) {
            String mode = pendingNativeScanMode;
            pendingNativeScanMode = "";
            if (granted) {
                Toast.makeText(this, "Запускаю нативный сканер Android", Toast.LENGTH_SHORT).show();
                launchNativeScanner(mode);
            } else {
                Toast.makeText(this, "Нативный сканер требует доступ к камере", Toast.LENGTH_LONG).show();
                dispatchNativeScanCancelled();
            }
        }
    }

    private final class AndroidScannerBridge {
        @JavascriptInterface
        public boolean isNativeScannerAvailable() {
            return true;
        }

        @JavascriptInterface
        public void startScan(String mode) {
            runOnUiThread(() -> startNativeScan(mode));
        }

        @JavascriptInterface
        public String appVersion() {
            return BuildConfig.VERSION_NAME;
        }

        @JavascriptInterface
        public boolean canOpenAppSettings() {
            return true;
        }

        @JavascriptInterface
        public void openAppSettings() {
            runOnUiThread(() -> showSetup("Настройки подключения APK. Здесь можно изменить адрес склада, проверить обновления и при необходимости сбросить подключение.", false));
        }

        @JavascriptInterface
        public String currentServerUrl() {
            return baseUrl == null ? "" : baseUrl;
        }

        @JavascriptInterface
        public void resetServerUrl() {
            runOnUiThread(MainActivity.this::clearSavedServer);
        }
    }

    /**
     * Блок 25: нативные возможности для PWA склада (window.AndroidNative).
     * Все методы безопасны для вызова из JS; тяжёлая работа — в отдельных потоках.
     */
    private final class NativeBridge {

        /** Сохранить файл (PDF/PRN/CSV/JSON) в «Загрузки». Возвращает true при успехе. */
        @JavascriptInterface
        public boolean saveFile(String name, String base64) {
            try {
                byte[] data = Base64.decode(base64 == null ? "" : base64, Base64.DEFAULT);
                if (data.length == 0) return false;
                String safe = (name == null || name.trim().isEmpty() ? "sklad-file" : name.trim())
                        .replaceAll("[\\/:*?\"<>|]", "_");
                final boolean saved = saveToDownloads(safe, data);
                final String shown = safe;
                runOnUiThread(() -> Toast.makeText(MainActivity.this,
                        saved ? "Сохранено: " + shown + " (Загрузки)" : "Не удалось сохранить файл",
                        Toast.LENGTH_LONG).show());
                return saved;
            } catch (Exception e) {
                return false;
            }
        }

        /** Прямая печать с телефона в сетевой принтер (raw ZPL/EPL на host:port 9100). */
        @JavascriptInterface
        public String printRaw(String host, int port, String base64) {
            try {
                if (TextUtils.isEmpty(host)) return "err: укажите IP принтера";
                final byte[] data = Base64.decode(base64 == null ? "" : base64, Base64.DEFAULT);
                if (data.length == 0) return "err: пустые данные печати";
                final String fHost = host.trim();
                final int fPort = port > 0 ? port : 9100;
                final String[] result = {"err: таймаут соединения"};
                Thread t = new Thread(() -> {
                    Socket s = new Socket();
                    try {
                        s.connect(new InetSocketAddress(fHost, fPort), 6000);
                        s.setSoTimeout(6000);
                        OutputStream os = s.getOutputStream();
                        os.write(data);
                        os.flush();
                        result[0] = "ok:" + data.length;
                    } catch (Exception e) {
                        result[0] = "err: " + e.getMessage();
                    } finally {
                        try { s.close(); } catch (Exception ignored) { }
                    }
                });
                t.start();
                t.join(9000);
                return result[0];
            } catch (Exception e) {
                return "err: " + e.getMessage();
            }
        }

        /** Не гасить экран (удобно при длительном сканировании). */
        @JavascriptInterface
        public void keepAwake(boolean enable) {
            runOnUiThread(() -> {
                if (enable) {
                    getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                } else {
                    getWindow().clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                }
            });
        }

        /** Короткая вибрация (фидбек сканирования/ошибки). */
        @JavascriptInterface
        public void vibrate(int ms) {
            vibrateFeedback();
        }

        @JavascriptInterface
        public void toast(String message) {
            runOnUiThread(() -> Toast.makeText(MainActivity.this,
                    message == null ? "" : message, Toast.LENGTH_SHORT).show());
        }

        /** Информация о приложении: версия, сервер. */
        @JavascriptInterface
        public String appInfo() {
            JSONObject o = new JSONObject();
            try {
                o.put("version", BuildConfig.VERSION_NAME);
                o.put("server", baseUrl == null ? "" : baseUrl);
                o.put("platform", "android");
            } catch (Exception ignored) { }
            return o.toString();
        }
    }

    private boolean saveToDownloads(String name, byte[] data) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                ContentValues cv = new ContentValues();
                cv.put(MediaStore.Downloads.DISPLAY_NAME, name);
                cv.put(MediaStore.Downloads.MIME_TYPE, mimeFor(name));
                cv.put(MediaStore.Downloads.IS_PENDING, 1);
                Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
                if (uri == null) return false;
                try (OutputStream os = getContentResolver().openOutputStream(uri)) {
                    if (os == null) return false;
                    os.write(data);
                    os.flush();
                }
                cv.clear();
                cv.put(MediaStore.Downloads.IS_PENDING, 0);
                getContentResolver().update(uri, cv, null, null);
                return true;
            }
            // Android 6–9: папка приложения (доступна файловым менеджерам, без разрешений)
            File dir = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
            if (dir == null) dir = getFilesDir();
            if (dir == null) return false;
            if (!dir.exists()) dir.mkdirs();
            File out = new File(dir, name);
            try (FileOutputStream fos = new FileOutputStream(out)) {
                fos.write(data);
                fos.flush();
            }
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    private String mimeFor(String name) {
        String n = (name == null ? "" : name).toLowerCase();
        if (n.endsWith(".pdf")) return "application/pdf";
        if (n.endsWith(".prn") || n.endsWith(".zpl") || n.endsWith(".epl") || n.endsWith(".txt")) return "text/plain";
        if (n.endsWith(".json")) return "application/json";
        if (n.endsWith(".csv")) return "text/csv";
        if (n.endsWith(".png")) return "image/png";
        if (n.endsWith(".jpg") || n.endsWith(".jpeg")) return "image/jpeg";
        if (n.endsWith(".mp4")) return "video/mp4";
        return "application/octet-stream";
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
