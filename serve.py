#!/usr/bin/env python3
"""Serve FitterCalcs on the LAN and over Tailscale Funnel HTTPS.

The calculator is the Android asset folder. Installers come from dist/
when a built file is there, otherwise from ~/backups/sprinkler-pipe-chart.
Accounts and job history live in accounts.py.
"""

import json
import os
import socket
import socketserver
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import accounts

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "app" / "src" / "main" / "assets"
BACKUP = Path.home() / "backups" / "sprinkler-pipe-chart"
DIST = ROOT / "dist"
HOST = "0.0.0.0"
PORT = int(os.environ.get("FITTERCALCS_PORT") or 8745)


def installer_path(built_name, backup_name):
    built = DIST / built_name
    if built.is_file() and built.stat().st_size > 0:
        return built
    return BACKUP / backup_name


DOWNLOADS = {
    "FitterCalcs.apk": (
        installer_path("FitterCalcs.apk", "FitterCalcs-2.45.apk"),
        "application/vnd.android.package-archive",
    ),
    "FitterCalcs-Setup.exe": (
        installer_path("FitterCalcs-Setup.exe", "FitterCalcs-Setup.exe"),
        "application/vnd.microsoft.portable-executable",
    ),
    "FitterCalcs-linux.tar.gz": (
        installer_path("FitterCalcs-linux.tar.gz", "FitterCalcs-linux.tar.gz"),
        "application/gzip",
    ),
}

INSTALL_NOTES = {
    "FitterCalcs.apk": "Android 7 or newer, build 2.46. It signs in to this server. If Android says this is a different app, uninstall the old FitterCalcs once, then open this file and allow install from this source.",
    "FitterCalcs-Setup.exe": "64-bit Windows 10 or 11, build 2.46. Portable app, no admin wizard. It signs in to this server. Replace the old program with this file.",
    "FitterCalcs-linux.tar.gz": "Linux build 2.46. It signs in to this server. Unpack it and run install.sh. Needs Python 3, GTK 3, and WebKitGTK 4.1.",
}


def lan_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.168.1.1", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def install_page():
    items = []
    for filename, (path, _ctype) in DOWNLOADS.items():
        if path.is_file():
            note = INSTALL_NOTES[filename]
            items.append(
                "<li><a href=\"/download/%s\">%s</a> — %s</li>"
                % (filename, filename, note)
            )
    listing = "\n".join(items) or "<li>No installer files are on this PC.</li>"
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FitterCalcs install</title>
<style>
  body { margin: 0; padding: 28px 22px 48px; background: #1a1613; color: #f4efe8;
         font: 18px/1.45 sans-serif; }
  main { max-width: 38rem; }
  a { color: #e8c56b; }
  h1 { font-size: 1.45rem; margin: 0 0 0.6rem; }
  ul { padding-left: 1.2rem; }
  li { margin: 0.7rem 0; }
</style>
</head>
<body>
<main>
  <h1>FitterCalcs</h1>
  <p><a href="/">Open the calculator</a> in this browser.</p>
  <p>These files are build 2.46. They sign in to this server. Install the one for the device. An app already on a phone or a Windows PC does not switch over by itself, and its GitHub update check is still on 2.45.</p>
  <ul>
    %s
  </ul>
</main>
</body>
</html>
""" % (listing,)
    return html.encode("utf-8")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _route(self):
        path = unquote(urlsplit(self.path).path)
        if path == "":
            path = "/"
        while "//" in path:
            path = path.replace("//", "/")
        return path

    def do_GET(self):
        if self._api("GET"):
            return
        self._dispatch(True)

    def do_HEAD(self):
        if self._route().startswith("/api/"):
            self.send_error(405, "Method not allowed")
            return
        self._dispatch(False)

    def do_POST(self):
        self._api("POST")

    def do_DELETE(self):
        self._api("DELETE")

    def _client_ip(self):
        ip = self.client_address[0]
        if ip in ("127.0.0.1", "::1"):
            forwarded = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            if forwarded:
                return forwarded[:64]
        return ip

    def _https(self):
        proto = (self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
        if proto == "https":
            return True
        host = (self.headers.get("Host") or "").lower()
        return host.endswith(".ts.net") or host.endswith(".ts.net:443")

    def _session_cookie(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            part = part.strip()
            if part.startswith("fc_session="):
                return part.split("=", 1)[1]
        return ""

    def _api(self, method):
        path = self._route()
        if not path.startswith("/api/"):
            return False
        length = 0
        if method in ("POST", "DELETE", "PUT"):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0 or length > accounts.MAX_BODY:
                self._json(413, {"error": "That upload is too large."})
                return True
        raw = self.rfile.read(length) if length else b""
        data = {}
        if raw:
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json(400, {"error": "The request was not valid."})
                return True
            if not isinstance(data, dict):
                self._json(400, {"error": "The request was not valid."})
                return True
        result = accounts.handle(
            method,
            path,
            data,
            self._session_cookie(),
            self._client_ip(),
            origin=self.headers.get("Origin") or "",
            host=self.headers.get("Host") or "",
        )
        self._json(result.status, result.body, session=result.session, clear=result.clear_session)
        return True

    def _json(self, status, obj, session=None, clear=False):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if session:
            bits = [
                "fc_session=%s" % session,
                "HttpOnly",
                "SameSite=Lax",
                "Path=/",
                "Max-Age=%d" % accounts.SESSION_SECONDS,
            ]
            if self._https():
                bits.append("Secure")
            self.send_header("Set-Cookie", "; ".join(bits))
        elif clear:
            self.send_header(
                "Set-Cookie",
                "fc_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0",
            )
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _dispatch(self, body):
        path = self._route()
        if path == "/update.json":
            self._send_path(ROOT / "update.json", "application/json", "update.json", False, body)
            return
        if path in ("/install", "/install/", "/download", "/download/"):
            self._send_bytes(install_page(), "text/html; charset=utf-8", body)
            return
        if path.startswith("/download/"):
            name = path[len("/download/"):]
            item = DOWNLOADS.get(name)
            if item and item[0].is_file() and "/" not in name:
                self._send_path(item[0], item[1], name, True, body)
                return
            self.send_error(404, "Not found")
            return
        if path != "/" and path.endswith("/"):
            self.send_error(404, "Not found")
            return
        if body:
            super().do_GET()
        else:
            super().do_HEAD()

    def _send_bytes(self, data, content_type, body):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if body:
            self.wfile.write(data)

    def _send_path(self, path, content_type, filename, attachment, body):
        if not path.is_file():
            self.send_error(404, "Not found")
            return
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        if attachment:
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % filename)
        self.end_headers()
        if not body:
            return
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(256 * 1024)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return


class Server(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer.server_bind calls getfqdn(), which stalls on 0.0.0.0.
        socketserver.TCPServer.server_bind(self)
        self.server_name = "maca"
        self.server_port = self.server_address[1]


def main():
    if not (WEB / "index.html").is_file():
        raise SystemExit("Missing %s" % (WEB / "index.html"))
    accounts.init_db()
    httpd = Server((HOST, PORT), Handler)
    ip = lan_ip()
    print("FitterCalcs http://%s:%s/" % (ip, PORT), flush=True)
    print("Install     http://%s:%s/install" % (ip, PORT), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
