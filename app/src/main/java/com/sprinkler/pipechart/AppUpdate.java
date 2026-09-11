package com.sprinkler.pipechart;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.os.Build;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

final class AppUpdate {
    static final String JSON_URL = "https://raw.githubusercontent.com/macski777/fittercalcs/main/update.json";
    static final String EXTRA_INSTALL = "install_update";
    static final String CHANNEL = "fittercalcs-updates";
    static final String APK_NAME = "FitterCalcs-update.apk";

    final int versionCode;
    final String versionName;
    final String apkUrl;
    final String notes;

    AppUpdate(int versionCode, String versionName, String apkUrl, String notes) {
        this.versionCode = versionCode;
        this.versionName = versionName == null ? "" : versionName;
        this.apkUrl = apkUrl == null ? "" : apkUrl;
        this.notes = notes == null ? "" : notes;
    }

    static long installedCode(Context ctx) {
        try {
            PackageInfo pi = ctx.getPackageManager().getPackageInfo(ctx.getPackageName(), 0);
            if (Build.VERSION.SDK_INT >= 28) return pi.getLongVersionCode();
            return pi.versionCode;
        } catch (Exception e) {
            return 0;
        }
    }

    static AppUpdate fetch() throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(JSON_URL).openConnection();
        try {
            c.setConnectTimeout(8000);
            c.setReadTimeout(12000);
            c.setInstanceFollowRedirects(true);
            c.setRequestProperty("User-Agent", "FitterCalcs");
            c.setRequestProperty("Accept", "application/json");
            int code = c.getResponseCode();
            if (code < 200 || code >= 300) throw new Exception("Update check HTTP " + code);
            String body = readAll(c.getInputStream());
            JSONObject o = new JSONObject(body);
            return new AppUpdate(
                o.getInt("versionCode"),
                o.optString("versionName", ""),
                o.optString("apkUrl", ""),
                o.optString("notes", "")
            );
        } finally {
            c.disconnect();
        }
    }

    static File downloadApk(Context ctx, String apkUrl) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(apkUrl).openConnection();
        try {
            c.setConnectTimeout(15000);
            c.setReadTimeout(60000);
            c.setInstanceFollowRedirects(true);
            c.setRequestProperty("User-Agent", "FitterCalcs");
            int code = c.getResponseCode();
            if (code < 200 || code >= 300) throw new Exception("Download HTTP " + code);
            File out = new File(ctx.getCacheDir(), APK_NAME);
            InputStream in = c.getInputStream();
            FileOutputStream fos = new FileOutputStream(out);
            try {
                byte[] buf = new byte[8192];
                int n;
                while ((n = in.read(buf)) > 0) fos.write(buf, 0, n);
                fos.flush();
            } finally {
                try { fos.close(); } catch (Exception ignored) {}
                try { in.close(); } catch (Exception ignored) {}
            }
            if (out.length() < 1000) throw new Exception("Download too small");
            return out;
        } finally {
            c.disconnect();
        }
    }

    static void notify(Context ctx, AppUpdate u) {
        try {
            NotificationManager nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm == null) return;
            if (Build.VERSION.SDK_INT >= 26) {
                NotificationChannel ch = new NotificationChannel(
                    CHANNEL, "FitterCalcs updates", NotificationManager.IMPORTANCE_DEFAULT);
                ch.setDescription("When a new FitterCalcs version is online");
                nm.createNotificationChannel(ch);
            }
            Intent open = new Intent(ctx, MainActivity.class);
            open.putExtra(EXTRA_INSTALL, true);
            open.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= 23) flags |= PendingIntent.FLAG_IMMUTABLE;
            PendingIntent pi = PendingIntent.getActivity(ctx, 17, open, flags);
            android.app.Notification.Builder b;
            if (Build.VERSION.SDK_INT >= 26) b = new android.app.Notification.Builder(ctx, CHANNEL);
            else b = new android.app.Notification.Builder(ctx);
            b.setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentTitle("FitterCalcs " + u.versionName + " is ready")
                .setContentText(u.notes.length() > 0 ? u.notes : "Tap to download and install")
                .setAutoCancel(true)
                .setContentIntent(pi);
            nm.notify(17, b.build());
        } catch (Exception ignored) {}
    }

    private static String readAll(InputStream in) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        return out.toString("UTF-8");
    }
}
