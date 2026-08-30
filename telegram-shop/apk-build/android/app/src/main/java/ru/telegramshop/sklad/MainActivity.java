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

/**
 * «Склад» — WebView-обёртка PWA /warehouse/.
 * Поддерживает:
 * - ввод адреса сервера при первом запуске,
 * - импорт адреса через deep link: sklad://setup?url=https://site/warehouse/
 * - мгновенное подключение через deep link: sklad://connect?url=https://site/warehouse/
 * - множественный выбор фото,
 * - экран «О приложении»/настройки по долгому нажатию.
 */
public class MainActivity extends AppCompatActivity {

    private static final String PREFS = "sklad_prefs";
    private static final String KEY_URL = "server_url";
    private static final int REQ_FILE = 1001;
    private static final String APP_UA = " SkladApp/1.0.2";

    private WebView webView;
    private View mainView, setupView;
    private EditText urlInput;
    private TextView setupError, appMeta, setupHint;
    private Button btnConnect, btnBack, btnReset;
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
        setupHint = findViewById(R.id.setup_hint);
        appMeta = findViewById(R.id.app_meta);
        btnConnect = findViewById(R.id.btn_connect);
        btnBack = findViewById(R.id.btn_back);
        btnReset = findViewById(R.id.btn_reset);

        configureWebView();
        updateMeta();

        btnConnect.setOnClickListener(v -> connect());
        btnBack.setOnClickListener(v -> loadWarehouse());
        btnReset.setOnClickListener(v -> clearSavedServer());

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
        prefs.edit().remove(KEY_URL).apply();
        urlInput.setText("");
        webView.loadUrl("about:blank");
        updateMeta();
        showSetup("Адрес сервера сброшен. Введите новый адрес или откройте ссылку настройки.");
    }

    private void setServerUrl(String raw, boolean showToast) {
        String url = normalize(raw);
        baseUrl = url;
        urlInput.setText(url);
        prefs.edit().putString(KEY_URL, url).apply();
        updateMeta();
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
        setupHint.setText("Можно открыть ссылку вида sklad://setup?url=https://ваш-домен/warehouse/\nили sklad://connect?url=https://ваш-домен/warehouse/ для мгновенного подключения.");
        btnBack.setVisibility(baseUrl == null || baseUrl.isEmpty() ? View.GONE : View.VISIBLE);
        btnReset.setVisibility(baseUrl == null || baseUrl.isEmpty() ? View.GONE : View.VISIBLE);
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
            showSetup("Настройки приложения. Можно сменить сервер, открыть ссылку настройки или сбросить сохранённый адрес.");
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
