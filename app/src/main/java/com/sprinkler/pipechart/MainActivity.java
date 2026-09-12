package com.sprinkler.pipechart;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ContentValues;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.Settings;
import android.util.Base64;
import android.view.Window;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;

public class MainActivity extends Activity {
    private WebView webView;
    private String pendingAction;
    private String pendingPayload;
    private String pendingName;
    private String pendingSubject;
    private String pendingBody;
    private final StringBuilder pngBuf = new StringBuilder();
    private AppUpdate pendingUpdate;
    private boolean updateCheckStarted;
    private boolean installAfterPermission;

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setStatusBarColor(Color.parseColor("#14110F"));
        webView = new WebView(this);
        webView.setBackgroundColor(Color.parseColor("#14110F"));
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setAllowFileAccess(true);
        try {
            settings.setAllowFileAccessFromFileURLs(true);
            settings.setAllowUniversalAccessFromFileURLs(true);
        } catch (Exception ignored) {}
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                if (!updateCheckStarted) {
                    updateCheckStarted = true;
                    checkForUpdate(false);
                }
                if (getIntent() != null && getIntent().getBooleanExtra(AppUpdate.EXTRA_INSTALL, false)) {
                    getIntent().removeExtra(AppUpdate.EXTRA_INSTALL);
                    downloadAndInstall();
                }
            }
        });
        webView.setDownloadListener((url, userAgent, contentDisposition, mimeType, contentLength) -> {
            if (url != null && url.startsWith("data:image")) {
                pendingAction = "save";
                pendingPayload = url;
                pendingName = "FitterCalcs-pump.png";
                runOnUiThread(() -> {
                    if (!ensureWritePermission()) return;
                    doSave(false);
                });
            }
        });
        webView.addJavascriptInterface(new Bridge(), "OnlyFitters");
        webView.loadUrl("file:///android_asset/index.html");
        setContentView(webView);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (intent != null && intent.getBooleanExtra(AppUpdate.EXTRA_INSTALL, false)) {
            intent.removeExtra(AppUpdate.EXTRA_INSTALL);
            downloadAndInstall();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (installAfterPermission) {
            installAfterPermission = false;
            downloadAndInstall();
        }
    }

    public class Bridge {
        @JavascriptInterface
        public void savePng(String dataUrl, String filename) {
            pendingAction = "save";
            pendingPayload = dataUrl;
            pendingName = filename;
            runOnUiThread(() -> {
                if (!ensureWritePermission()) return;
                doSave(false);
            });
        }

        @JavascriptInterface
        public void emailPng(String dataUrl, String filename, String subject, String body) {
            pendingAction = "email";
            pendingPayload = dataUrl;
            pendingName = filename;
            pendingSubject = subject;
            pendingBody = body;
            runOnUiThread(() -> {
                if (!ensureWritePermission()) return;
                doSave(true);
            });
        }

        @JavascriptInterface
        public void beginPng(String mode, String filename, String subject, String body) {
            pendingAction = mode;
            pendingName = filename;
            pendingSubject = subject;
            pendingBody = body;
            synchronized (pngBuf) {
                pngBuf.setLength(0);
            }
        }

        @JavascriptInterface
        public void appendPng(String chunk) {
            if (chunk == null) return;
            synchronized (pngBuf) {
                pngBuf.append(chunk);
            }
        }

        @JavascriptInterface
        public void finishPng() {
            synchronized (pngBuf) {
                pendingPayload = pngBuf.toString();
                pngBuf.setLength(0);
            }
            runOnUiThread(() -> {
                if (!ensureWritePermission()) return;
                doSave("email".equals(pendingAction));
            });
        }

        @JavascriptInterface
        public void emailText(String subject, String body) {
            pendingSubject = subject;
            pendingBody = body;
            runOnUiThread(() -> {
                Intent intent = new Intent(Intent.ACTION_SEND);
                intent.setType("text/plain");
                intent.putExtra(Intent.EXTRA_SUBJECT, pendingSubject == null ? "FitterCalcs report" : pendingSubject);
                intent.putExtra(Intent.EXTRA_TEXT, pendingBody == null ? "" : pendingBody);
                try {
                    startActivity(Intent.createChooser(intent, "Email report"));
                } catch (ActivityNotFoundException e) {
                    Toast.makeText(MainActivity.this, "No email app installed", Toast.LENGTH_LONG).show();
                }
            });
        }

        @JavascriptInterface
        public void toast(final String msg) {
            runOnUiThread(() -> Toast.makeText(MainActivity.this, msg, Toast.LENGTH_LONG).show());
        }

        @JavascriptInterface
        public void checkUpdate() {
            runOnUiThread(() -> checkForUpdate(true));
        }

        @JavascriptInterface
        public void installUpdate() {
            runOnUiThread(() -> downloadAndInstall());
        }
    }

    private void checkForUpdate(boolean fromUser) {
        if (fromUser) Toast.makeText(this, "Checking for update…", Toast.LENGTH_SHORT).show();
        final boolean user = fromUser;
        new Thread(() -> {
            try {
                final AppUpdate u = AppUpdate.fetch();
                long have = AppUpdate.installedCode(this);
                runOnUiThread(() -> {
                    if (u.versionCode <= have) {
                        if (user) Toast.makeText(this, "FitterCalcs is up to date (v" + haveName() + ")", Toast.LENGTH_SHORT).show();
                        return;
                    }
                    pendingUpdate = u;
                    askNotifyPermission();
                    AppUpdate.notify(this, u);
                    showUpdateBanner(u);
                    if (user) Toast.makeText(this, "Update v" + u.versionName + " is available", Toast.LENGTH_SHORT).show();
                });
            } catch (Exception e) {
                if (user) {
                    runOnUiThread(() -> Toast.makeText(this, "Could not check update (need internet)", Toast.LENGTH_LONG).show());
                }
            }
        }, "fittercalcs-update").start();
    }

    private String haveName() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "";
        }
    }

    private void showUpdateBanner(AppUpdate u) {
        if (webView == null) return;
        String js = "if(window.FitterCalcsUpdate)FitterCalcsUpdate.show("
            + JSONObject.quote(u.versionName) + ","
            + JSONObject.quote(u.notes) + ")";
        webView.evaluateJavascript(js, null);
    }

    private void askNotifyPermission() {
        if (Build.VERSION.SDK_INT < 33) return;
        if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) return;
        requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 93);
    }

    private void downloadAndInstall() {
        if (pendingUpdate == null || pendingUpdate.apkUrl.length() == 0) {
            checkForUpdate(true);
            return;
        }
        if (Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
            installAfterPermission = true;
            Toast.makeText(this, "Allow FitterCalcs to install updates, then return here", Toast.LENGTH_LONG).show();
            try {
                startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + getPackageName())));
            } catch (Exception e) {
                Toast.makeText(this, "Enable unknown-app installs for FitterCalcs in Settings", Toast.LENGTH_LONG).show();
            }
            return;
        }
        Toast.makeText(this, "Downloading FitterCalcs " + pendingUpdate.versionName + "…", Toast.LENGTH_SHORT).show();
        final String url = pendingUpdate.apkUrl;
        new Thread(() -> {
            try {
                File apk = AppUpdate.downloadApk(this, url);
                Uri uri = PngProvider.uriFor(getPackageName(), apk.getName());
                runOnUiThread(() -> {
                    Intent intent = new Intent(Intent.ACTION_VIEW);
                    intent.setDataAndType(uri, "application/vnd.android.package-archive");
                    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    try {
                        startActivity(intent);
                    } catch (Exception e) {
                        Toast.makeText(this, "Install failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
                    }
                });
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(this, "Download failed: " + e.getMessage(), Toast.LENGTH_LONG).show());
            }
        }, "fittercalcs-dl").start();
    }

    private boolean ensureWritePermission() {
        if (Build.VERSION.SDK_INT >= 29) return true;
        if (checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED) {
            return true;
        }
        requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, 91);
        return false;
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == 91 && grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            doSave("email".equals(pendingAction));
        } else if (requestCode == 91) {
            Toast.makeText(this, "Storage permission needed to save the chart", Toast.LENGTH_LONG).show();
        } else if (requestCode == 93 && pendingUpdate != null
            && grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            AppUpdate.notify(this, pendingUpdate);
        }
    }

    private byte[] decodePng(String dataUrl) {
        if (dataUrl == null) return null;
        int comma = dataUrl.indexOf(',');
        String b64 = comma >= 0 ? dataUrl.substring(comma + 1) : dataUrl;
        if (b64.trim().isEmpty()) return null;
        return Base64.decode(b64, Base64.DEFAULT);
    }

    private String safeName(String filename) {
        String name = filename == null ? "" : filename.trim();
        name = name.replace("\\", "_").replace("/", "_");
        if (name.isEmpty()) name = "FitterCalcs-pump.png";
        if (!name.toLowerCase().endsWith(".png")) name += ".png";
        return name;
    }

    private File writeCache(byte[] png, String filename) throws Exception {
        File file = new File(getCacheDir(), filename);
        try (FileOutputStream out = new FileOutputStream(file)) {
            out.write(png);
            out.flush();
        }
        return file;
    }

    private Uri writeGallery(byte[] png, String filename) throws Exception {
        if (Build.VERSION.SDK_INT >= 29) {
            ContentValues values = new ContentValues();
            values.put(MediaStore.Images.Media.DISPLAY_NAME, filename);
            values.put(MediaStore.Images.Media.MIME_TYPE, "image/png");
            values.put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/FitterCalcs");
            Uri uri = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values);
            if (uri == null) throw new Exception("Could not create Pictures/FitterCalcs file");
            OutputStream out = getContentResolver().openOutputStream(uri);
            if (out == null) throw new Exception("Could not write file");
            try {
                out.write(png);
                out.flush();
            } finally {
                out.close();
            }
            return uri;
        }
        File dir = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES), "FitterCalcs");
        if (!dir.exists() && !dir.mkdirs()) throw new Exception("Could not make Pictures/FitterCalcs");
        File file = new File(dir, filename);
        try (FileOutputStream out = new FileOutputStream(file)) {
            out.write(png);
        }
        ContentValues values = new ContentValues();
        values.put(MediaStore.Images.Media.DATA, file.getAbsolutePath());
        values.put(MediaStore.Images.Media.MIME_TYPE, "image/png");
        Uri uri = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values);
        return uri != null ? uri : Uri.fromFile(file);
    }

    private void doSave(boolean email) {
        try {
            byte[] png = decodePng(pendingPayload);
            if (png == null || png.length == 0) throw new Exception("Empty image");
            String name = safeName(pendingName);
            File cache = writeCache(png, name);
            Uri shareUri = PngProvider.uriFor(getPackageName(), cache.getName());
            Uri galleryUri = null;
            try {
                galleryUri = writeGallery(png, name);
            } catch (Exception galleryErr) {
                if (!email) throw galleryErr;
            }
            if (email) {
                Intent intent = new Intent(Intent.ACTION_SEND);
                intent.setType("image/png");
                intent.putExtra(Intent.EXTRA_STREAM, shareUri);
                intent.putExtra(Intent.EXTRA_SUBJECT, pendingSubject == null ? "FitterCalcs pump curve" : pendingSubject);
                intent.putExtra(Intent.EXTRA_TEXT, pendingBody == null ? "" : pendingBody);
                intent.setClipData(ClipData.newRawUri(name, shareUri));
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                Intent chooser = Intent.createChooser(intent, "Email FitterCalcs report");
                chooser.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                try {
                    startActivity(chooser);
                } catch (ActivityNotFoundException e) {
                    Toast.makeText(this, "No email app installed", Toast.LENGTH_LONG).show();
                }
            } else {
                String where = galleryUri != null ? "Pictures/FitterCalcs" : cache.getAbsolutePath();
                Toast.makeText(this, "Saved to " + where, Toast.LENGTH_LONG).show();
            }
        } catch (Exception e) {
            Toast.makeText(this, "Save failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }
}
