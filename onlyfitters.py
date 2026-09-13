#!/usr/bin/env python3
"""FitterCalcs — pipe, hydro, tanks, pump curves, AS 1851."""
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gdk, GLib, Gtk, WebKit2

APP_ID = "org.onlyfitters.app"
APP_NAME = "FitterCalcs"
APP_VERSION = "2.30"
APP_TITLE = "%s %s" % (APP_NAME, APP_VERSION)
APP_DIR = Path(__file__).resolve().parent
HTML = APP_DIR / "index.html"
ICON = APP_DIR / "onlyfitters.png"
PICTURES = Path.home() / "Pictures" / "FitterCalcs"
WEBKIT_DIR = Path.home() / ".local" / "share" / "onlyfitters" / "webkit"

BRIDGE_JS = r"""
window.FitterCalcsPC = true;
window.OnlyFitters = {
  savePng: function(dataUrl, filename) {
    window.webkit.messageHandlers.onlyfitters.postMessage(JSON.stringify({
      op: "save", dataUrl: dataUrl, filename: filename
    }));
  },
  emailPng: function(dataUrl, filename, subject, body) {
    window.webkit.messageHandlers.onlyfitters.postMessage(JSON.stringify({
      op: "email", dataUrl: dataUrl, filename: filename, subject: subject, body: body
    }));
  },
  emailText: function(subject, body) {
    window.webkit.messageHandlers.onlyfitters.postMessage(JSON.stringify({
      op: "emailText", subject: subject, body: body
    }));
  },
  toast: function(msg) {
    window.webkit.messageHandlers.onlyfitters.postMessage(JSON.stringify({
      op: "toast", msg: msg
    }));
  },
  fullscreen: function(on) {
    window.webkit.messageHandlers.onlyfitters.postMessage(JSON.stringify({
      op: "fullscreen", on: !!on
    }));
  }
};
"""


def notify(msg):
    try:
        subprocess.Popen(
            ["notify-send", "-a", APP_TITLE, APP_TITLE, msg],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def decode_png(data_url):
    if not data_url:
        raise ValueError("empty image")
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    return base64.b64decode(data_url)


def safe_name(name):
    name = name or "FitterCalcs-pump.png"
    name = os.path.basename(name)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    if not name.lower().endswith(".png"):
        name += ".png"
    return name


def save_png(data_url, filename):
    PICTURES.mkdir(parents=True, exist_ok=True)
    path = PICTURES / safe_name(filename)
    path.write_bytes(decode_png(data_url))
    return path


def email_text(subject, body):
    subject = subject or "FitterCalcs report"
    body = body or ""
    try:
        subprocess.Popen(
            ["xdg-email", "--subject", subject, "--body", body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        subprocess.Popen(
            ["xdg-open", "mailto:?subject=" + subject],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def email_png(data_url, filename, subject, body):
    path = save_png(data_url, filename)
    subject = subject or "FitterCalcs pump curve"
    body = body or ""
    cmd = [
        "xdg-email",
        "--subject",
        subject,
        "--body",
        body,
        "--attach",
        str(path),
    ]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        subprocess.Popen(
            ["xdg-open", f"mailto:?subject={subject}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return path


class OnlyFitters(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        GLib.set_prgname("FitterCalcs")

    def do_activate(self):
        if self.get_active_window():
            self.get_active_window().present()
            return

        win = Gtk.ApplicationWindow(application=self, title=APP_TITLE)
        win.set_default_size(460, 860)
        win.set_name("FitterCalcs")
        self.win = win
        if ICON.exists():
            win.set_icon_from_file(str(ICON))

        ucm = WebKit2.UserContentManager()
        ucm.register_script_message_handler("onlyfitters")
        ucm.connect("script-message-received::onlyfitters", self.on_message)
        script = WebKit2.UserScript(
            BRIDGE_JS,
            WebKit2.UserContentInjectedFrames.ALL_FRAMES,
            WebKit2.UserScriptInjectionTime.START,
            None,
            None,
        )
        ucm.add_script(script)

        WEBKIT_DIR.mkdir(parents=True, exist_ok=True)
        data_mgr = WebKit2.WebsiteDataManager(
            base_data_directory=str(WEBKIT_DIR / "data"),
            base_cache_directory=str(WEBKIT_DIR / "cache"),
        )
        ctx = WebKit2.WebContext.new_with_website_data_manager(data_mgr)
        try:
            web = WebKit2.WebView.new_with_context_and_user_content_manager(ctx, ucm)
        except Exception:
            web = WebKit2.WebView.new_with_user_content_manager(ucm)
        settings = web.get_settings()
        settings.set_enable_javascript(True)
        try:
            settings.set_enable_html5_local_storage(True)
            settings.set_enable_html5_database(True)
        except Exception:
            pass
        settings.set_allow_file_access_from_file_urls(True)
        try:
            settings.set_allow_universal_access_from_file_urls(True)
        except Exception:
            pass
        try:
            settings.set_enable_page_cache(False)
        except Exception:
            pass
        try:
            settings.set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)
        except Exception:
            pass
        web.set_background_color(Gdk.RGBA(0.08, 0.07, 0.06, 1))
        stamp = str(int(HTML.stat().st_mtime)) if HTML.exists() else "1"
        web.load_uri(HTML.resolve().as_uri() + "?v=" + stamp)

        web.set_hexpand(True)
        web.set_vexpand(True)
        win.add(web)
        win.show_all()
        web.grab_focus()

    def on_message(self, _manager, result):
        try:
            payload = result.get_js_value().to_string()
            msg = json.loads(payload)
        except Exception as exc:
            notify("Message error: %s" % exc)
            return
        op = msg.get("op")
        try:
            if op == "save":
                path = save_png(msg.get("dataUrl"), msg.get("filename"))
                notify("Saved %s" % path)
            elif op == "email":
                path = email_png(
                    msg.get("dataUrl"),
                    msg.get("filename"),
                    msg.get("subject"),
                    msg.get("body"),
                )
                notify("Opening email with %s" % path.name)
            elif op == "emailText":
                email_text(msg.get("subject"), msg.get("body"))
                notify("Opening email")
            elif op == "toast":
                notify(msg.get("msg") or "")
            elif op == "fullscreen":
                win = self.get_active_window() or getattr(self, "win", None)
                if win:
                    if msg.get("on"):
                        win.fullscreen()
                    else:
                        win.unfullscreen()
        except Exception as exc:
            notify("Failed: %s" % exc)


def main():
    if not HTML.exists():
        sys.stderr.write("Missing %s\n" % HTML)
        sys.exit(1)
    app = OnlyFitters()
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main()
