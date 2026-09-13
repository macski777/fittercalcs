#!/usr/bin/env python3
"""FitterCalcs desktop — Windows (WebView2) and fallback Linux/macOS."""
import base64
import os
import re
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path
from urllib.parse import quote

APP_NAME = "FitterCalcs"
APP_VERSION = "2.30"


def app_dir():
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    here = Path(__file__).resolve().parent
    assets = here.parent / "app" / "src" / "main" / "assets"
    if (assets / "index.html").exists():
        return assets
    if (here / "index.html").exists():
        return here
    return here.parent


def pictures_dir():
    home = Path.home()
    if sys.platform == "win32":
        return Path(os.environ.get("USERPROFILE", home)) / "Pictures" / APP_NAME
    return home / "Pictures" / APP_NAME


def decode_png(data_url):
    if not data_url:
        raise ValueError("empty image")
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    return base64.b64decode(data_url)


def safe_name(name):
    name = name or "FitterCalcs-report.png"
    name = os.path.basename(name)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    if not name.lower().endswith(".png"):
        name += ".png"
    return name


def save_png(data_url, filename):
    dest = pictures_dir()
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / safe_name(filename)
    path.write_bytes(decode_png(data_url))
    return path


def open_path(path):
    path = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def mailto(subject, body):
    subject = subject or "%s report" % APP_NAME
    body = body or ""
    webbrowser.open("mailto:?subject=%s&body=%s" % (quote(subject), quote(body)))


def notify(msg):
    msg = msg or ""
    try:
        if sys.platform == "win32":
            return
        if sys.platform == "darwin":
            subprocess.Popen(
                ["osascript", "-e", 'display notification "%s" with title "%s"' % (msg.replace('"', ""), APP_NAME)]
            )
        else:
            subprocess.Popen(["notify-send", "-a", APP_NAME, APP_NAME, msg])
    except Exception:
        pass


class Api:
    def save_png(self, data_url, filename):
        path = save_png(data_url, filename)
        notify("Saved %s" % path)
        return str(path)

    def email_png(self, data_url, filename, subject, body):
        path = save_png(data_url, filename)
        mailto(subject, (body or "") + "\n\nChart saved to:\n" + str(path))
        open_path(path)
        notify("Saved %s and opened email" % path.name)
        return str(path)

    def email_text(self, subject, body):
        mailto(subject, body)
        notify("Opening email")

    def toast(self, msg):
        notify(msg)

    def fullscreen(self, on):
        try:
            import webview
            wins = webview.windows
            if wins:
                wins[0].toggle_fullscreen()
        except Exception:
            pass


def main():
    import webview

    root = app_dir()
    html = root / "index.html"
    if not html.exists():
        sys.stderr.write("Missing %s\n" % html)
        sys.exit(1)
    icon = root / "logo.png"
    if not icon.exists():
        icon = Path(__file__).resolve().parent / "fittercalcs.ico"
    stamp = str(int(html.stat().st_mtime))
    url = html.resolve().as_uri() + "?v=" + stamp
    webview.create_window(
        "%s %s" % (APP_NAME, APP_VERSION),
        url=url,
        js_api=Api(),
        width=480,
        height=880,
        min_size=(380, 640),
        background_color="#14110F",
        text_select=True,
    )
    kwargs = {"debug": False}
    if sys.platform == "win32":
        kwargs["gui"] = "edgechromium"
    webview.start(**kwargs)


if __name__ == "__main__":
    main()
