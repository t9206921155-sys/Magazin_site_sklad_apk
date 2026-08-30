package ru.telegramshop.sklad;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
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

/**
 * «Склад» — WebView-обёртка PWA /warehouse/ (аналог сборки PWABuilder "APK без TWA").
 * Первый запуск: нативный экран ввода адреса сервера.
 * Сменить сервер: долгое нажатие на экран склада.
 * Загрузка фото (input type=file) пробрасывается в системный выбор файлов/камеры.
 */
public class MainActivity extends AppCompatActivity {

    private static final String PREFS = "sklad_prefs";
    private static final String KEY_URL = "server_url";
    private static final int REQ_FILE = 1001;
    private static final String APP_UA = " SkladApp/1.0.1";

    private WebView webView;
    private View mainView, setupView;
    private EditText urlInput;
    private TextView setupError;
    private Button btnConnect, btnBack;
    private SharedPreferences prefs;
    private String baseUrl = "";
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
        btnConnect = findViewById(R.id.btn_connect);
        btnBack = findViewById(R.id.btn_back);

        configureWebView();

        btnConnect.setOnClickListener(v -> connect());
        btnBack.setOnClickListener(v -> loadWarehouse());

        String saved = prefs.getString(KEY_URL, "");
        if (saved.isEmpty() && BuildConfig.WAREHOUSE_URL != null && !BuildConfig.WAREHOUSE_URL.isEmpty()) {
            saved = BuildConfig.WAREHOUSE_URL;
        }
        if (!saved.isEmpty()) {
            baseUrl = saved;
            urlInput.setText(saved);
            prefs.edit().putString(KEY_URL, saved).apply();
            loadWarehouse();
        } else {
            showSetup("Введите адрес вашего сервера.");
        }
    }

    private void connect() {
        String raw = urlInput.getText().toString().trim();
        if (raw.isEmpty()) {
            setupError.setText("Введите адрес сервера, например https://myshop.ru/warehouse/");
            setupError.setVisibility(View.VISIBLE);
            return;
        }
        String url = normalize(raw);
        baseUrl = url;
        urlInput.setText(url);
        prefs.edit().putString(KEY_URL, url).apply();
        loadWarehouse();
    }

    /** Добавляет https:// и путь /warehouse/, если путь не указан. */
    private String normalize(String raw) {
        String s = raw.trim();
        if (!s.startsWith("http://") && !s.startsWith("https://")) s = "https://" + s;
        try {
            Uri u = Uri.parse(s);
            String path = u.getPath() == null ? "" : u.getPath();
            if (path.isEmpty() || path.equals("/")) {
                s = s.replaceAll("/+$", "");
                s += "/warehouse/";
            }
        } catch (Exception ignored) { }
        return s;
    }

    private void loadWarehouse() {
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

    private void showSetup(String error) {
        mainView.setVisibility(View.GONE);
        setupView.setVisibility(View.VISIBLE);
        setupError.setVisibility(error == null ? View.GONE : View.VISIBLE);
        if (error != null) setupError.setText(error);
        btnBack.setVisibility(baseUrl.isEmpty() ? View.GONE : View.VISIBLE);
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
                // Внутренняя навигация по складу — в WebView
                if (isInternalUrl(url)) return false;
                // Внешние ссылки (t.me, wa.me, оплата и т.п.) — в системный браузер/приложение
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

        // Долгое нажатие — экран настройки сервера
        webView.setOnLongClickListener(v -> {
            showSetup("Настройка сервера. Введите новый адрес и нажмите «Подключиться».");
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
            if (!baseUrl.isEmpty()) { loadWarehouse(); return; }
        }
        if (webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }
}
