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
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.util.Base64;
import android.view.Window;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceError;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.Locale;

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
    private boolean usedLocal;
    private TextToSpeech tts;
    private boolean ttsReady;
    private SpeechRecognizer recognizer;
    private boolean recognizing;
    private boolean assistantOverlayOpen;
    private static final int REQ_RECORD_AUDIO = 92;
    private static final int REQ_VOICE_INPUT = 94;
    private static final String LOCAL_PAGE = "file:///android_asset/index.html";

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

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request != null && request.isForMainFrame()) loadLocal();
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
        webView.addJavascriptInterface(new VoiceBridge(), "FCVoice");
        setContentView(webView);
        initTts();
        openCalculator();
    }

    private void openCalculator() {
        final String server = readServerUrl();
        if (server.isEmpty()) {
            loadLocal();
            return;
        }
        new Thread(() -> {
            final boolean up = serverReachable(server);
            runOnUiThread(() -> {
                if (isFinishing() || webView == null) return;
                if (up) webView.loadUrl(server);
                else loadLocal();
            });
        }).start();
    }

    private void loadLocal() {
        if (usedLocal || webView == null) return;
        usedLocal = true;
        webView.loadUrl(LOCAL_PAGE);
    }

    private String readServerUrl() {
        try (InputStream in = getAssets().open("server.url")) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[256];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            String text = out.toString("UTF-8").trim();
            int nl = text.indexOf('\n');
            if (nl >= 0) text = text.substring(0, nl).trim();
            if (!text.startsWith("https://") || text.indexOf(' ') >= 0 || text.length() > 200) return "";
            if (!text.endsWith("/")) text = text + "/";
            return text;
        } catch (Exception e) {
            return "";
        }
    }

    private boolean serverReachable(String server) {
        for (int i = 0; i < 3; i++) {
            HttpURLConnection conn = null;
            try {
                conn = (HttpURLConnection) new URL(server + "api/setup").openConnection();
                conn.setConnectTimeout(6000);
                conn.setReadTimeout(6000);
                conn.setInstanceFollowRedirects(true);
                int code = conn.getResponseCode();
                if (code >= 200 && code < 500) return true;
            } catch (Exception ignored) {
            } finally {
                if (conn != null) conn.disconnect();
            }
        }
        return false;
    }

    @Override
    public void onBackPressed() {
        if (assistantOverlayOpen && webView != null) {
            webView.evaluateJavascript(
                    "window.FCAssistantBack && window.FCAssistantBack()",
                    null
            );
            return;
        }
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

    private void initTts() {
        tts = new TextToSpeech(this, status -> {
            if (status != TextToSpeech.SUCCESS) {
                ttsReady = false;
                notifyVoiceState("error", "Text to speech is not available on this phone.");
                return;
            }
            ttsReady = true;
            int result = tts.setLanguage(new Locale("en", "AU"));
            if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                tts.setLanguage(Locale.getDefault());
            }
            tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                @Override
                public void onStart(String utteranceId) {
                    notifyVoiceState("start", "");
                }

                @Override
                public void onDone(String utteranceId) {
                    notifyVoiceState("done", "");
                }

                @Override
                public void onError(String utteranceId) {
                    notifyVoiceState("error", "Text to speech stopped.");
                }
            });
        });
    }

    private void notifyVoiceState(String state, String message) {
        if (webView == null) return;
        final String js = "window.FCVoiceOnDone && window.FCVoiceOnDone("
                + JSONObject.quote(state) + ","
                + JSONObject.quote(message == null ? "" : message) + ");";
        webView.post(() -> {
            if (webView != null) webView.evaluateJavascript(js, null);
        });
    }

    private void notifyDictation(String state, String message) {
        if (webView == null) return;
        final String js = "window.FCVoiceOnDictation && window.FCVoiceOnDictation("
                + JSONObject.quote(state) + ","
                + JSONObject.quote(message == null ? "" : message) + ");";
        webView.post(() -> {
            if (webView != null) webView.evaluateJavascript(js, null);
        });
    }

    private void notifyTranscript(String text, boolean isFinal) {
        if (webView == null) return;
        final String js = "window.FCVoiceOnText && window.FCVoiceOnText("
                + JSONObject.quote(text == null ? "" : text) + ","
                + (isFinal ? "true" : "false") + ");";
        webView.post(() -> {
            if (webView != null) webView.evaluateJavascript(js, null);
        });
    }

    private boolean voicePageAllowed() {
        if (webView == null) return false;
        String url = webView.getUrl();
        if (url == null) return false;
        return url.startsWith("https://")
                || url.startsWith("http://")
                || url.startsWith("file:///android_asset/");
    }

    private void startRecognition() {
        if (recognizer == null && !SpeechRecognizer.isRecognitionAvailable(this)) {
            notifyDictation("error", "Speech recognition is not available on this phone.");
            return;
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_RECORD_AUDIO);
            return;
        }
        if (recognizer == null) {
            recognizer = SpeechRecognizer.createSpeechRecognizer(this);
            recognizer.setRecognitionListener(new RecognitionListener() {
                @Override
                public void onReadyForSpeech(Bundle params) {
                    if (recognizing) notifyDictation("listening", "");
                }

                @Override
                public void onBeginningOfSpeech() {}

                @Override
                public void onRmsChanged(float rmsdB) {}

                @Override
                public void onBufferReceived(byte[] buffer) {}

                @Override
                public void onEndOfSpeech() {
                    if (recognizing) notifyDictation("processing", "");
                }

                @Override
                public void onError(int error) {
                    if (!recognizing) return;
                    recognizing = false;
                    notifyDictation("error", recognitionError(error));
                }

                @Override
                public void onResults(Bundle results) {
                    if (!recognizing) return;
                    recognizing = false;
                    ArrayList<String> matches = results == null ? null
                            : results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    String text = matches != null && !matches.isEmpty() ? matches.get(0) : "";
                    notifyTranscript(text, true);
                    notifyDictation("done", "");
                }

                @Override
                public void onPartialResults(Bundle partialResults) {
                    if (!recognizing) return;
                    ArrayList<String> matches = partialResults == null ? null
                            : partialResults.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    if (matches != null && !matches.isEmpty()) notifyTranscript(matches.get(0), false);
                }

                @Override
                public void onEvent(int eventType, Bundle params) {}
            });
        }
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-AU");
        intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
        intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
        recognizing = true;
        notifyDictation("listening", "");
        try {
            recognizer.startListening(intent);
        } catch (Exception error) {
            recognizing = false;
            notifyDictation("error", "Speech recognition could not start.");
        }
    }

    private void startVoiceInput() {
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-AU");
        intent.putExtra(RecognizerIntent.EXTRA_PROMPT, "Ask Stillo a question");
        intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
        notifyDictation("listening", "");
        try {
            startActivityForResult(intent, REQ_VOICE_INPUT);
        } catch (ActivityNotFoundException error) {
            // No system voice dialog. Fall back to the in-app recognizer.
            startRecognition();
        } catch (Exception error) {
            notifyDictation("error", "Dictation could not start.");
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_VOICE_INPUT) return;
        String text = "";
        if (data != null) {
            ArrayList<String> results = data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
            if (results != null && !results.isEmpty()) {
                text = results.get(0);
            }
        }
        if (text != null && !text.trim().isEmpty()) {
            notifyTranscript(text, true);
            notifyDictation("done", "");
        } else {
            notifyDictation(
                    "error",
                    resultCode == RESULT_CANCELED ? "Dictation cancelled." : "No speech was recognised."
            );
        }
    }

    private String recognitionError(int error) {        switch (error) {
            case SpeechRecognizer.ERROR_AUDIO:
                return "There was a problem with the microphone.";
            case SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS:
                return "Microphone permission is required.";
            case SpeechRecognizer.ERROR_NETWORK:
            case SpeechRecognizer.ERROR_NETWORK_TIMEOUT:
            case SpeechRecognizer.ERROR_SERVER:
                return "Speech recognition needs an internet connection.";
            case SpeechRecognizer.ERROR_NO_MATCH:
                return "I didn't catch that. Tap the mic and try again.";
            case SpeechRecognizer.ERROR_SPEECH_TIMEOUT:
                return "I didn't hear anything. Tap the mic and try again.";
            case SpeechRecognizer.ERROR_RECOGNIZER_BUSY:
                return "The microphone is busy. Try again.";
            default:
                return "Dictation stopped.";
        }
    }

    @Override
    protected void onDestroy() {
        if (tts != null) {
            tts.stop();
            tts.shutdown();
            tts = null;
        }
        if (recognizer != null) {
            recognizer.destroy();
            recognizer = null;
        }
        super.onDestroy();
    }

    public class VoiceBridge {
        @JavascriptInterface
        public boolean available() {
            return true;
        }

        @JavascriptInterface
        public void openUrl(String url) {
            if (url == null) return;
            String value = url.trim();
            if (!(value.startsWith("http://") || value.startsWith("https://"))) return;
            try {
                Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(value));
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                startActivity(intent);
            } catch (Exception ignored) {
            }
        }

        @JavascriptInterface
        public void setOverlay(boolean open) {
            assistantOverlayOpen = open;
        }

        @JavascriptInterface
        public void speak(final String text) {
            final String clean = text == null ? "" : text.trim();
            if (clean.isEmpty()) return;
            runOnUiThread(() -> {
                if (!voicePageAllowed()) {
                    notifyVoiceState("error", "Voice is only available inside the FitterCalcs app.");
                    return;
                }
                if (tts == null || !ttsReady) {
                    notifyVoiceState("error", "Voice is still starting. Try again.");
                    return;
                }
                tts.stop();
                Bundle params = new Bundle();
                params.putString(TextToSpeech.Engine.KEY_PARAM_UTTERANCE_ID, "fc-answer");
                int result = tts.speak(clean, TextToSpeech.QUEUE_FLUSH, params, "fc-answer");
                if (result == TextToSpeech.ERROR) {
                    notifyVoiceState("error", "Text to speech could not start.");
                }
            });
        }

        @JavascriptInterface
        public void stopSpeaking() {
            runOnUiThread(() -> {
                if (tts != null) tts.stop();
            });
        }

        @JavascriptInterface
        public void startDictation() {
            runOnUiThread(() -> {
                if (voicePageAllowed()) startVoiceInput();
            });
        }

        @JavascriptInterface
        public void stopDictation() {
            runOnUiThread(() -> {
                recognizing = false;
                if (recognizer != null) recognizer.cancel();
                notifyDictation("done", "");
            });
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
        if (requestCode == REQ_RECORD_AUDIO) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                startRecognition();
            } else {
                notifyDictation("error", "Microphone permission was denied.");
            }
            return;
        }
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
