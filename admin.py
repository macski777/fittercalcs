#!/usr/bin/env python3
"""Window on this PC to see FitterCalcs accounts, reports, and email them."""

import base64
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("JavaScriptCore", "4.1")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, WebKit2

import accounts

PAGE = Path(__file__).resolve().parent / "app" / "src" / "main" / "assets" / "index.html"
LOGO = PAGE.parent / "logo.png"
PICTURES = Path.home() / "Pictures" / "FitterCalcs"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STILLO_CONFIG = Path.home() / ".config" / "fittercalcs" / "assistant.json"


def assistant_config_path():
    override = (os.environ.get("FITTERCALCS_ASSISTANT_CONFIG") or "").strip()
    return Path(override).expanduser() if override else STILLO_CONFIG


def load_stillo_users(path=None):
    path = path or assistant_config_path()
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return set()
    names = data.get("allowed_users") if isinstance(data, dict) else None
    if not isinstance(names, list):
        return set()
    return {str(name).strip().lower() for name in names if str(name).strip()}


def stillo_allowed(username, path=None):
    return str(username or "").strip().lower() in load_stillo_users(path)


def set_stillo_access(username, enabled, path=None):
    """Add or remove one name in assistant.json, preserving every other key."""
    name = str(username or "").strip()
    if not name:
        raise ValueError("No such account.")
    path = path or assistant_config_path()
    if not enabled and not path.is_file():
        return []
    data = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text("utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError):
            data = {}
    names = data.get("allowed_users")
    names = [str(item).strip() for item in names if str(item).strip()] if isinstance(names, list) else []
    kept = [item for item in names if item.lower() != name.lower()]
    if enabled:
        kept.append(name)
    data["allowed_users"] = kept
    data.setdefault("allow_all_admins", True)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return kept


APP_CSS = b"""
.fittercalcs {
    background-color: #14110f;
    color: #f4ede4;
}
.fittercalcs box {
    background-color: transparent;
}
.fittercalcs scrolledwindow, .fittercalcs viewport {
    background-color: #14110f;
    color: #f4ede4;
}
.fittercalcs headerbar {
    background-color: #1c1815;
    background-image: none;
    color: #f4ede4;
    border-bottom: 1px solid #3a322c;
    box-shadow: none;
}
.fittercalcs headerbar .title {
    color: #f4ede4;
    font-weight: 700;
}
.fittercalcs headerbar .subtitle {
    color: #a89b8c;
}
.fittercalcs .hub-name {
    color: #f4ede4;
    font-weight: 700;
    font-size: 16px;
}
.fittercalcs .hub-sub {
    color: #a89b8c;
    font-size: 11px;
}
.fittercalcs label {
    color: #f4ede4;
}
.fittercalcs .heading {
    color: #e8b86d;
    font-weight: 700;
    font-size: 15px;
}
.fittercalcs .title {
    color: #f4ede4;
    font-weight: 700;
}
.fittercalcs .dim {
    color: #a89b8c;
}
.fittercalcs .detail {
    font-family: monospace;
    font-size: 13px;
}
.fittercalcs list {
    background-color: #1c1815;
}
.fittercalcs list row, .fittercalcs list row box {
    background-color: #1c1815;
    background-image: none;
    color: #f4ede4;
    border-bottom: 1px solid #3a322c;
}
.fittercalcs list row:hover {
    background-color: #241f1b;
}
.fittercalcs list row:selected,
.fittercalcs list row:selected:hover,
.fittercalcs list row:selected box {
    background-color: #d1243a;
    background-image: none;
    color: #ffffff;
}
.fittercalcs list row:selected label,
.fittercalcs list row:selected .title {
    color: #ffffff;
}
.fittercalcs list row:selected .dim {
    color: #ffd4d8;
}
.fittercalcs button {
    background-color: #241f1b;
    background-image: none;
    color: #f4ede4;
    border: 1px solid #3a322c;
    border-radius: 8px;
    padding: 6px 10px;
    box-shadow: none;
}
.fittercalcs button:hover {
    background-color: #2a2420;
    color: #f4ede4;
}
.fittercalcs button:active, .fittercalcs button:checked {
    background-color: #d1243a;
    background-image: none;
    color: #ffffff;
    border-color: #d1243a;
}
.fittercalcs button:disabled {
    background-color: #1c1815;
    color: #6a5d50;
    border-color: #3a322c;
}
.fittercalcs headerbar button {
    background-color: transparent;
    background-image: none;
    border: none;
    color: #f4ede4;
    box-shadow: none;
}
.fittercalcs headerbar button:hover {
    background-color: #d1243a;
    color: #ffffff;
}
.fittercalcs headerbar button:checked,
.fittercalcs headerbar button:active {
    background-color: #d1243a;
    color: #ffffff;
}
.fittercalcs entry {
    background-color: #1a1613;
    color: #f4ede4;
    border: 1px solid #3a322c;
    border-radius: 8px;
    caret-color: #e8b86d;
}
.fittercalcs textview, .fittercalcs textview text {
    background-color: #1c1815;
    color: #f4ede4;
}
.fittercalcs paned separator, paned.report-split separator {
    background-color: #3a322c;
    min-height: 10px;
    min-width: 8px;
}
.fittercalcs scrollbar trough {
    background-color: transparent;
}
.fittercalcs scrollbar slider {
    background-color: #3a322c;
    border-radius: 99px;
    min-width: 8px;
    min-height: 8px;
}
.fittercalcs expander title {
    color: #a89b8c;
}
.fittercalcs combobox button, .fittercalcs combobox box {
    background-color: #1a1613;
    color: #f4ede4;
}
"""


def theme(widget):
    widget.get_style_context().add_class("fittercalcs")
    return widget
REPORT_FN = r"""
(function() {
window.__fcAdminReport = function(kind, state) {
  function packError(message) {
    return JSON.stringify({ error: message });
  }
  try {
    state = state || {};
    if (kind === "pump") {
      applyPumpState(state, state.id || "");
      var curves = [];
      if (Array.isArray(state.curves) && state.curves.length) {
        curves = state.curves;
      } else if (Array.isArray(state.pts)) {
        curves = [{ driver: "electric", pts: state.pts }];
      }
      curves = curves.map(function(c) {
        return {
          driver: c.driver === "diesel" ? "diesel" : "electric",
          pts: (c.pts || []).map(function(p) {
            return { q: Number(p.q), p: Number(p.p) };
          }).filter(function(p) { return isFinite(p.q) && isFinite(p.p); })
        };
      }).filter(function(c) { return c.pts.length >= 2; });
      if (!curves.length) return packError("Add at least two curve points before a report can be drawn.");
      var job = state.jobName || "";
      var year = String(state.year || "");
      var pump = state.pumpId || "";
      var req = null;
      if (state.req && isFinite(Number(state.req.q)) && isFinite(Number(state.req.p))) {
        req = { q: Number(state.req.q), p: Number(state.req.p), note: state.req.note || state.reqNote || "" };
      }
      var verdict = pumpSetVerdict(curves, req);
      var subject = subjectWithResult("Fire pump performance estimate", job, verdict);
      if (year) subject += " (" + year + ")";
      var safe = (job || "pump").replace(/[^A-Za-z0-9-_]+/g, "_").replace(/^_+|_+$/g, "") || "pump";
      return JSON.stringify({
        png: composePumpReportPng(curves, job, year, pump, req),
        subject: subject,
        body: pumpReportText(curves, job, year, pump, req),
        fname: "FitterCalcs-" + safe + "-" + (year || "report") + ".png"
      });
    }
    if (kind === "flow") {
      if (typeof applyFlowState !== "function" || typeof composeFlowReportPng !== "function") {
        return packError("This flow test could not be opened.");
      }
      applyFlowState(state, state.id || "");
      var flowSite = state.site || "";
      var flowVerdictNow = flowVerdict();
      var flowSubject = subjectWithResult(flowSys().label + " flow test", flowSite, flowVerdictNow);
      return JSON.stringify({
        png: composeFlowReportPng(),
        subject: flowSubject,
        body: flowReportText(),
        fname: reportFile("flow", flowSite)
      });
    }
    if (kind === "hydro") {
      applyHydroInput(state, state.id || "");
      var hydro = hydroReportPack();
      if (!hydro) return packError("This hydro calc needs a flow, a length, and a pipe size.");
      return JSON.stringify(hydro);
    }
    if (kind === "tank") {
      applyTankInput(state, state.id || "");
      var tank = tankReportPack();
      if (!tank) return packError("This tank calc needs a tank size before a report can be drawn.");
      return JSON.stringify({
        png: tank.png, subject: tank.subject, body: tank.body, fname: tank.fname
      });
    }
    if (kind === "fan") {
      if (typeof applyFanInput !== "function" || typeof fanReportPack !== "function") {
        return packError("This fan test could not be opened.");
      }
      applyFanInput(state, state.id || "");
      var fan = fanReportPack();
      if (!fan) return packError("This fan test needs fan points and room figures before a report can be drawn.");
      return JSON.stringify({
        png: fan.png, subject: fan.subject, body: fan.body, fname: fan.fname
      });
    }
    return packError("This file has no report.");
  } catch (err) {
    return packError(String(err && err.message ? err.message : err));
  }
};
return "ok";
})()
"""

KINDS = (("pump", "Pump"), ("hydro", "Hydro"), ("tank", "Tank"), ("fan", "Fan"), ("flow", "Flow"))
KIND_LABEL = dict(KINDS)
CALC_FIELDS = (
    ("pump", "onlyfitters-pump-jobs", "onlyfitters-pump-draft"),
    ("hydro", "onlyfitters-hydro-jobs", "onlyfitters-hydro-draft"),
    ("tank", "onlyfitters-tank-jobs", "onlyfitters-tank-draft"),
    ("fan", "onlyfitters-fan-jobs", "onlyfitters-fan-draft"),
    ("flow", "onlyfitters-flow-jobs", "onlyfitters-flow-draft"),
)
CALC_BRIDGE_JS = r"""
window.FitterCalcsPC = true;
window.OnlyFitters = {
  savePng: function(dataUrl, filename) {
    window.webkit.messageHandlers.fitterhub.postMessage(JSON.stringify({
      op: "save", dataUrl: dataUrl, filename: filename
    }));
  },
  emailPng: function(dataUrl, filename, subject, body) {
    window.webkit.messageHandlers.fitterhub.postMessage(JSON.stringify({
      op: "email", dataUrl: dataUrl, filename: filename, subject: subject, body: body
    }));
  },
  emailText: function(subject, body) {
    window.webkit.messageHandlers.fitterhub.postMessage(JSON.stringify({
      op: "emailText", subject: subject, body: body
    }));
  },
  toast: function(msg) {
    window.webkit.messageHandlers.fitterhub.postMessage(JSON.stringify({
      op: "toast", msg: msg
    }));
  },
  fullscreen: function(on) {
    window.webkit.messageHandlers.fitterhub.postMessage(JSON.stringify({
      op: "fullscreen", on: !!on
    }));
  },
  shareJob: function(kind, id, label) {
    window.webkit.messageHandlers.fitterhub.postMessage(JSON.stringify({
      op: "share", kind: kind, id: id, label: label
    }));
  },
  sync: function() {
    window.webkit.messageHandlers.fitterhub.postMessage(JSON.stringify({ op: "sync" }));
  }
};
window.fcHubRead = function() {
  var keys = __KEYS__;
  var out = {};
  for (var i = 0; i < keys.length; i++) {
    var value = null;
    try { value = localStorage.getItem(keys[i]); } catch (e) { value = null; }
    out[keys[i]] = value;
  }
  return JSON.stringify(out);
};
window.fcHubFlush = function() {
  try { if (typeof autosavePump === "function") autosavePump(); } catch (e) {}
  try { if (typeof autosaveHydro === "function") autosaveHydro(); } catch (e) {}
  try { if (typeof autosaveTank === "function") autosaveTank(); } catch (e) {}
  try { if (window.autosaveFan) window.autosaveFan(); } catch (e) {}
  return window.fcHubRead();
};
"""


def calculator_bridge_js():
    keys = []
    for _kind, jobs_key, draft_key in CALC_FIELDS:
        keys.append(jobs_key)
        keys.append(draft_key)
    return CALC_BRIDGE_JS.replace("__KEYS__", json.dumps(keys))


def calculator_inject_script(state):
    payload = json.dumps(state, ensure_ascii=False)
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return (
        "(function(){"
        "var err='';"
        "try{fcApply(" + payload + ",true);}catch(e){err=String(e&&e.message||e);}"
        "var read='';"
        "try{read=window.fcHubRead();}catch(e){if(!err)err=String(e&&e.message||e);}"
        "return JSON.stringify({err:err,read:read});"
        "})()"
    )


def _storage_blank(raw):
    return raw is None or (isinstance(raw, str) and raw.strip() in ("", "null"))


def _snapshot_blank(snap):
    for _kind, jobs_key, draft_key in CALC_FIELDS:
        if not _storage_blank(snap.get(jobs_key)) or not _storage_blank(snap.get(draft_key)):
            return False
    return True


def _jobs_from_storage(raw):
    """Return the saved-job list, or None when this kind must be left alone."""
    if _storage_blank(raw) or not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    return parsed


def _draft_from_storage(raw):
    if _storage_blank(raw) or not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def write_calculator_snapshot(user_id, text):
    """Mirror one calculator snapshot into accounts.db.

    Returns True when a row changed, False when the snapshot was stored as-is,
    and None when it was ignored. An empty read is ignored so a new WebView
    cannot wipe the person's jobs.
    """
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None
    try:
        snap = json.loads(text) if isinstance(text, str) else None
    except json.JSONDecodeError:
        return None
    if not isinstance(snap, dict) or _snapshot_blank(snap):
        return None
    accounts.init_db()
    conn = accounts.connect()
    changed = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        now_ms = int(time.time() * 1000)
        for kind, jobs_key, draft_key in CALC_FIELDS:
            jobs = _jobs_from_storage(snap.get(jobs_key))
            if jobs is not None:
                keep = set()
                valid = []
                for rec in jobs:
                    if not isinstance(rec, dict):
                        continue
                    job_id = str(rec.get("id") or "")
                    if not accounts.ID_RE.match(job_id):
                        continue
                    keep.add(job_id)
                    if len(valid) < 80:
                        valid.append((job_id, rec))
                blocked_recs = []
                for job_id, rec in valid:
                    updated = accounts._as_ms(rec.get("updated"))
                    if updated is None:
                        continue
                    fingerprint = accounts._job_fingerprint(rec)
                    if accounts._removed_blocks(conn, user_id, kind, job_id, updated, fingerprint):
                        keep.discard(job_id)
                        blocked_recs.append(rec)
                        continue
                    stored = dict(rec)
                    stored["id"] = job_id
                    stored["updated"] = updated
                    blob = json.dumps(stored, separators=(",", ":"), ensure_ascii=False)
                    if len(blob) > 200_000:
                        continue
                    row = conn.execute(
                        "SELECT payload FROM jobs WHERE user_id = ? AND kind = ? AND job_id = ?",
                        (user_id, kind, job_id),
                    ).fetchone()
                    if row and row["payload"] == blob:
                        continue
                    accounts._clear_removed(conn, user_id, kind, job_id)
                    conn.execute(
                        """INSERT INTO jobs (user_id, kind, job_id, payload, updated_at)
                           VALUES (?,?,?,?,?)
                           ON CONFLICT(user_id, kind, job_id) DO UPDATE SET
                             payload = excluded.payload,
                             updated_at = excluded.updated_at""",
                        (user_id, kind, job_id, blob, updated),
                    )
                    changed = True
                deleted_recs = []
                rows = conn.execute(
                    "SELECT job_id, payload FROM jobs WHERE user_id = ? AND kind = ?",
                    (user_id, kind),
                ).fetchall()
                for row in rows:
                    if row["job_id"] in keep:
                        continue
                    parsed = None
                    try:
                        parsed = json.loads(row["payload"])
                    except json.JSONDecodeError:
                        parsed = None
                    conn.execute(
                        "DELETE FROM jobs WHERE user_id = ? AND kind = ? AND job_id = ?",
                        (user_id, kind, row["job_id"]),
                    )
                    prior = accounts._as_ms(parsed.get("updated")) if isinstance(parsed, dict) else None
                    stamp = now_ms if prior is None else max(now_ms, prior)
                    finger = accounts._job_fingerprint(parsed) if isinstance(parsed, dict) else ""
                    accounts._tombstone(conn, user_id, kind, row["job_id"], stamp, finger)
                    if isinstance(parsed, dict):
                        deleted_recs.append(parsed)
                    changed = True
                for rec in blocked_recs + deleted_recs:
                    if accounts._drop_same_draft(conn, user_id, kind, rec, now_ms):
                        changed = True
                if accounts._collapse_duplicate_jobs(conn, user_id, kind, now_ms):
                    changed = True
            draft = _draft_from_storage(snap.get(draft_key))
            if draft is None:
                continue
            updated = accounts._as_ms(draft.get("updated"))
            if updated is None:
                continue
            if accounts._removed_blocks(
                conn, user_id, kind, "", updated, accounts._job_fingerprint(draft)
            ):
                continue
            blob = json.dumps(draft, separators=(",", ":"), ensure_ascii=False)
            if len(blob) > 200_000:
                continue
            row = conn.execute(
                "SELECT payload FROM drafts WHERE user_id = ? AND kind = ?",
                (user_id, kind),
            ).fetchone()
            if row and row["payload"] == blob:
                continue
            accounts._clear_removed(conn, user_id, kind, "")
            conn.execute(
                """INSERT INTO drafts (user_id, kind, payload, updated_at)
                   VALUES (?,?,?,?)
                   ON CONFLICT(user_id, kind) DO UPDATE SET
                     payload = excluded.payload,
                     updated_at = excluded.updated_at""",
                (user_id, kind, blob, updated),
            )
            changed = True
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return changed


def open_calculator_email(data_url, filename, subject, body):
    """Open the mail app with the report attached. No address is required."""
    path, _raw = save_report_png(data_url, filename)
    subject = subject or "FitterCalcs report"
    body = body or ""
    if shutil.which("xdg-email"):
        subprocess.Popen(
            ["xdg-email", "--subject", subject, "--body", body, "--attach", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.Popen(
            ["xdg-open", "mailto:?subject=%s" % subject],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return path


def open_db():
    accounts.init_db()
    if not accounts.DB.is_file():
        return None
    return sqlite3.connect(f"file:{accounts.DB}?mode=ro", uri=True)


def clean_email(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 200 or not EMAIL_RE.match(text):
        raise ValueError("Enter a real email address, or leave it blank.")
    return text


def create_person(username, password, email, confirm, stillo=False):
    if password != confirm:
        raise ValueError("The two passwords do not match.")
    address = clean_email(email)
    accounts.init_db()
    conn = accounts.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        created = accounts._insert_user(conn, username, password, False)
        conn.execute("UPDATE users SET email = ? WHERE id = ?", (address, created["id"]))
        conn.commit()
        created["email"] = address
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    if stillo:
        try:
            set_stillo_access(created["username"], True)
        except OSError as exc:
            raise ValueError("Account created, but Ask Stillo access could not be saved: %s" % exc) from exc
    return created


def reset_person(user_id, password, confirm):
    if password != confirm:
        raise ValueError("The two passwords do not match.")
    return accounts.reset_password(user_id, password)


def delete_person(user_id):
    accounts.init_db()
    conn = accounts.connect()
    try:
        row = conn.execute(
            "SELECT id, username, is_admin FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            raise ValueError("No such account.")
        if row["is_admin"]:
            raise ValueError("The first account can't be removed.")
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        try:
            set_stillo_access(row["username"], False)
        except OSError:
            pass
        return row["username"]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_file(user_id, item):
    kind = item.get("kind")
    if kind not in accounts.KINDS:
        raise ValueError("This file has no report.")
    draft = bool(item.get("draft"))
    job_id = "" if draft else str(item.get("job_id") or "")
    if not draft and not accounts.ID_RE.match(job_id):
        raise ValueError("This saved job has no id.")
    accounts.init_db()
    accounts.remove_job(user_id, kind, job_id, draft)


def remove_saved_picture(path):
    if not path:
        return
    picture = Path(path)
    try:
        picture.resolve().relative_to(PICTURES.resolve())
    except ValueError:
        return
    if picture.is_file():
        picture.unlink()


def save_report_png(data_url, filename):
    if not data_url or "," not in data_url:
        raise ValueError("This report has no picture.")
    raw = base64.b64decode(data_url.split(",", 1)[1])
    if not raw.startswith(b"\x89PNG"):
        raise ValueError("The report picture was not a PNG.")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename or "FitterCalcs-report.png").name)
    if not name.lower().endswith(".png"):
        name += ".png"
    PICTURES.mkdir(parents=True, exist_ok=True)
    path = PICTURES / name
    path.write_bytes(raw)
    return path, raw


def send_report(path, subject, body, address):
    address = clean_email(address)
    if not address:
        raise ValueError("Enter the email address to send this report to.")
    subject = subject or "FitterCalcs report"
    body = body or ""
    if shutil.which("xdg-email"):
        subprocess.Popen(
            ["xdg-email", "--subject", subject, "--body", body, "--attach", str(path), address],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return "Opened your email app with the report attached."
    subprocess.Popen(
        ["xdg-open", "mailto:%s?subject=%s" % (address, subject)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return "Opened a blank email. The report picture is saved at %s" % path


def when(value):
    if not isinstance(value, (int, float)) or value <= 0:
        return ""
    seconds = value / 1000 if value > 10_000_000_000 else value
    try:
        return datetime.fromtimestamp(seconds).strftime("%d %b %Y %H:%M")
    except (OverflowError, OSError, ValueError):
        return ""


def read_json(payload):
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def job_title(kind, data, draft):
    if kind == "pump":
        name = str(data.get("jobName") or "").strip() or str(data.get("pumpId") or "").strip()
    else:
        name = str(data.get("site") or "").strip()
    if name:
        return name
    return "Draft, not named yet" if draft else "Untitled"


def add_line(lines, label, value):
    if value is None:
        return
    text = str(value).strip()
    if text:
        lines.append("%s: %s" % (label, text))


def job_lines(kind, data):
    lines = []
    if data.get("sharedBy"):
        add_line(lines, "From", data.get("sharedBy"))
    if kind == "pump":
        add_line(lines, "Job", data.get("jobName"))
        add_line(lines, "Year", data.get("year"))
        add_line(lines, "Pump", data.get("pumpId"))
        req = data.get("req")
        if isinstance(req, dict):
            flow = str(req.get("q") or "").strip()
            pressure = str(req.get("p") or "").strip()
            if flow or pressure:
                lines.append("Duty: %s L/s at %s kPa" % (flow, pressure))
            add_line(lines, "Note", req.get("note"))
        add_line(lines, "Note", data.get("reqNote"))
        points = data.get("pts") if isinstance(data.get("pts"), list) else []
        if points:
            lines.append("Curve points:")
            for point in points[:40]:
                if isinstance(point, dict):
                    lines.append("  %s L/s, %s kPa" % (point.get("q", ""), point.get("p", "")))
    elif kind == "hydro":
        add_line(lines, "Site", data.get("site"))
        add_line(lines, "Pipe", data.get("sched"))
        add_line(lines, "Size", data.get("nps"))
        add_line(lines, "Flow", data.get("Q"))
        add_line(lines, "Length", data.get("L"))
        add_line(lines, "Elbows", data.get("elb"))
        add_line(lines, "Rise", data.get("rise"))
        add_line(lines, "C", data.get("C"))
        add_line(lines, "Result", data.get("summary"))
    elif kind == "flow":
        add_line(lines, "Site", data.get("site"))
        add_line(lines, "System", data.get("system"))
        req = data.get("req")
        if isinstance(req, dict):
            add_line(lines, "Required flow", req.get("q"))
            add_line(lines, "Required residual", req.get("p"))
        points = data.get("pts") if isinstance(data.get("pts"), list) else []
        for point in points[:40]:
            if isinstance(point, dict):
                bits = []
                if point.get("name"):
                    bits.append(str(point.get("name")))
                if point.get("q") not in (None, ""):
                    bits.append("%s L/s" % point.get("q"))
                if point.get("residual") not in (None, ""):
                    bits.append("%s kPa" % point.get("residual"))
                if bits:
                    lines.append("  " + ", ".join(bits))
        add_line(lines, "Result", data.get("summary"))
    elif kind == "fan":
        add_line(lines, "Client", data.get("client"))
        add_line(lines, "Enclosure", data.get("enclosure"))
        add_line(lines, "Job number", data.get("jobNo"))
        add_line(lines, "Tested by", data.get("tester"))
        add_line(lines, "Agent", data.get("agent"))
        add_line(lines, "Result", data.get("summary"))
    else:
        add_line(lines, "Site", data.get("site"))
        add_line(lines, "System", data.get("sys"))
        add_line(lines, "Hazard", data.get("hazard"))
        add_line(lines, "Tanks", data.get("count"))
        add_line(lines, "Top", data.get("top"))
        add_line(lines, "Bottom", data.get("bot"))
        add_line(lines, "Hydrant flow", data.get("Qh"))
        add_line(lines, "Sprinkler flow", data.get("Qs"))
        add_line(lines, "Infill", data.get("Qi"))
        add_line(lines, "Result", data.get("summary"))
    stamp = when(data.get("updated"))
    if stamp:
        lines.append("Saved: %s" % stamp)
    if not lines:
        lines.append("Nothing filled in yet.")
    return "\n".join(lines)


def file_record(kind, payload, updated_at, draft, job_id=""):
    data = read_json(payload)
    return {
        "kind": kind,
        "draft": draft,
        "job_id": job_id,
        "title": job_title(kind, data, draft),
        "updated": updated_at or data.get("updated") or 0,
        "detail": job_lines(kind, data),
        "state": data,
    }


def accounts_signature():
    """Cheap fingerprint of the jobs table, used to spot external syncs."""
    conn = open_db()
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(updated_at), 0) FROM jobs"
        ).fetchone()
        return (int(row[0]), int(row[1]))
    finally:
        conn.close()


def load_people():
    conn = open_db()
    if conn is None:
        return []
    try:
        people = []
        rows = conn.execute(
            """SELECT id, username, is_admin, created_at, email
               FROM users ORDER BY username COLLATE NOCASE"""
        ).fetchall()
        kind_order = {name: index for index, (name, _label) in enumerate(KINDS)}
        for user_id, username, is_admin, created_at, email in rows:
            files = []
            for kind, job_id, payload, updated_at in conn.execute(
                """SELECT kind, job_id, payload, updated_at FROM jobs
                   WHERE user_id = ? ORDER BY updated_at DESC""",
                (user_id,),
            ):
                files.append(file_record(kind, payload, updated_at, False, job_id))
            for kind, payload, updated_at in conn.execute(
                "SELECT kind, payload, updated_at FROM drafts WHERE user_id = ?",
                (user_id,),
            ):
                files.append(file_record(kind, payload, updated_at, True))
            files.sort(key=lambda item: (
                item["draft"],
                kind_order.get(item["kind"], 9),
                -int(item["updated"] or 0),
            ))
            people.append({
                "id": user_id,
                "username": username,
                "admin": bool(is_admin),
                "email": email or "",
                "created": when(created_at),
                "files": files,
            })
        return people
    finally:
        conn.close()


def person_summary(person, stillo=None):
    saved = sum(1 for item in person["files"] if not item["draft"])
    drafts = sum(1 for item in person["files"] if item["draft"])
    role = "Admin" if person["admin"] else "Person"
    bits = [role]
    username = str(person.get("username") or "").strip().lower()
    if person["admin"] or (stillo is not None and username in stillo):
        bits.append("Stillo")
    if person.get("email"):
        bits.append(person["email"])
    bits.append("%d saved" % saved)
    if drafts:
        bits.append("%d draft%s" % (drafts, "" if drafts == 1 else "s"))
    if person["created"]:
        bits.append("since %s" % person["created"])
    return " · ".join(bits)


def file_matches(item, mode):
    if mode == "saved":
        return not item["draft"]
    if mode == "draft":
        return bool(item["draft"])
    return True


def file_summary(item):
    label = KIND_LABEL.get(item["kind"], item["kind"])
    state = "draft" if item["draft"] else "saved"
    stamp = when(item["updated"])
    text = "%s %s" % (label, state)
    if stamp:
        text = "%s · %s" % (text, stamp)
    return text


def js_text(view, result):
    value = view.run_javascript_finish(result)
    return value.get_js_value().to_string()


class ReportEngine:
    def __init__(self):
        self.ready = False
        self.failed = False
        self.fail_detail = ""
        self.token = 0
        self.pending = None
        settings = WebKit2.Settings()
        settings.set_enable_javascript(True)
        settings.set_allow_file_access_from_file_urls(True)
        settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
        self.view = WebKit2.WebView(settings=settings)
        self.host = Gtk.OffscreenWindow()
        self.host.set_default_size(480, 640)
        self.host.add(self.view)
        self.view.connect("load-changed", self.on_load)
        self.view.connect("load-failed", self.on_fail)
        self.host.show_all()
        self.view.load_uri(PAGE.resolve().as_uri())

    def on_fail(self, _view, _event, uri, error):
        self.failed = True
        self.fail_detail = getattr(error, "message", None) or str(error) or "unknown error"
        self._finish({"error": "The report page did not open."})
        return True

    def on_load(self, view, event):
        if event != WebKit2.LoadEvent.FINISHED or self.ready or self.failed:
            return
        view.run_javascript(REPORT_FN, None, self.on_ready, None)

    def on_ready(self, view, result, _data):
        try:
            text = js_text(view, result)
        except Exception as exc:
            self.failed = True
            self.fail_detail = str(exc)
            self._finish({"error": "The report page did not open."})
            return
        if text != "ok":
            self.failed = True
            self.fail_detail = text or "installer returned nothing"
            self._finish({"error": "The report page did not open."})
            return
        self.ready = True
        self._kick()

    def request(self, kind, state, callback):
        self.token += 1
        token = self.token
        self.pending = (token, kind, state, callback)
        if self.failed:
            self._finish({"error": "The report page did not open."})
            return
        if self.ready:
            self._kick()
            return
        GLib.timeout_add(12000, self._give_up, token)

    def _give_up(self, token):
        if self.pending and self.pending[0] == token and not self.ready and not self.failed:
            self.failed = True
            self.fail_detail = self.fail_detail or "timed out"
            self._finish({"error": "The report page did not open."})
        return False

    def _kick(self):
        if not self.pending or not self.ready:
            return
        token, kind, state, callback = self.pending
        script = "window.__fcAdminReport(%s, %s)" % (json.dumps(kind), json.dumps(state))
        self.view.run_javascript(script, None, self.on_result, (token, callback))

    def on_result(self, view, result, user):
        token, callback = user
        if not self.pending or token != self.pending[0]:
            return
        try:
            text = js_text(view, result)
            data = json.loads(text)
            if not isinstance(data, dict):
                data = {"error": "The report page did not answer."}
        except Exception:
            data = {"error": "The report could not be drawn."}
        self.pending = None
        callback(data)

    def _finish(self, data):
        if not self.pending:
            return
        _token, _kind, _state, callback = self.pending
        self.pending = None
        callback(data)


class AdminWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Fitter-Hub")
        theme(self)
        self.set_default_size(1100, 900)
        self.set_hide_titlebar_when_maximized(False)
        self.people = []
        self._selected_user = None
        self._selected_file = None
        self.file_filter = "all"
        self.report_png = None
        self.report_full = None
        self.report_subject = ""
        self.report_body = ""
        self.report_name = ""
        self.enlarge_window = None
        self._preview_width = 0
        self._split_ready = False
        self.calc_user_id = None
        self.calc_page_owner = None
        self.calc_paused = True
        self.calc_generation = 0
        self.calc_baseline = None
        self.calc_poll_busy = False
        self.history_dirty = False
        self.calc_timer = 0
        self._page_loaded = False
        self._calc_pending = None
        self.reports = ReportEngine()

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        brand = Gtk.Box(spacing=8)
        if LOGO.is_file():
            mark = Gtk.Image()
            mark.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(LOGO), 32, 32, True))
            brand.pack_start(mark, False, False, 0)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        hub = Gtk.Label(label="Fitter-Hub", xalign=0)
        hub.get_style_context().add_class("hub-name")
        sub = Gtk.Label(label="Calculator and accounts on this PC", xalign=0)
        sub.get_style_context().add_class("hub-sub")
        names.pack_start(hub, False, False, 0)
        names.pack_start(sub, False, False, 0)
        brand.pack_start(names, False, False, 0)
        header.set_title("Fitter-Hub")
        header.set_custom_title(brand)
        refresh = Gtk.Button.new_with_label("Refresh")
        refresh.connect("clicked", lambda _button: self.on_refresh())
        header.pack_end(refresh)
        self.header = header
        self.set_titlebar(header)
        self.set_title("Fitter-Hub")
        style = Gtk.CssProvider()
        style.load_from_data(APP_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(),
            style,
            Gtk.STYLE_PROVIDER_PRIORITY_USER,
        )

        pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        pane.set_position(320)
        pane.set_wide_handle(True)

        people_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        people_box.set_margin_top(12)
        people_box.set_margin_bottom(12)
        people_box.set_margin_start(12)
        people_box.set_margin_end(6)
        people_head = Gtk.Box(spacing=6)
        people_label = Gtk.Label(label="People", xalign=0)
        people_label.get_style_context().add_class("heading")
        people_label.set_hexpand(True)
        people_refresh = Gtk.Button.new_with_label("Refresh")
        people_refresh.set_tooltip_text("Reload accounts and reports from the server")
        people_refresh.connect("clicked", lambda _button: self.reload())
        people_head.pack_start(people_label, True, True, 0)
        people_head.pack_end(people_refresh, False, False, 0)
        self.people_list = Gtk.ListBox()
        self.people_list.set_selection_mode(Gtk.SelectionMode.BROWSE)
        self.people_list.connect("row-selected", self.on_person)
        people_scroll = Gtk.ScrolledWindow()
        people_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        people_scroll.set_vexpand(True)
        people_scroll.add(self.people_list)
        people_actions = Gtk.Box(spacing=6)
        create_btn = Gtk.Button.new_with_label("Create account")
        create_btn.connect("clicked", lambda _button: self.create_account())
        self.remove_btn = Gtk.Button.new_with_label("Remove account")
        self.remove_btn.set_sensitive(False)
        self.remove_btn.connect("clicked", lambda _button: self.remove_account())
        people_actions.pack_start(create_btn, True, True, 0)
        people_actions.pack_start(self.remove_btn, True, True, 0)
        self.reset_btn = Gtk.Button.new_with_label("Reset password")
        self.reset_btn.set_sensitive(False)
        self.reset_btn.connect("clicked", lambda _button: self.reset_password_dialog())
        people_box.pack_start(people_head, False, False, 0)
        people_box.pack_start(people_scroll, True, True, 0)
        people_box.pack_start(people_actions, False, False, 0)
        people_box.pack_start(self.reset_btn, False, False, 0)
        self.stillo_check = Gtk.CheckButton(label="Allow Ask Stillo")
        self.stillo_check.set_sensitive(False)
        self.stillo_check.connect("toggled", self.on_stillo_toggle)
        self.stillo_note = Gtk.Label(label="", xalign=0)
        self.stillo_note.get_style_context().add_class("dim")
        people_box.pack_start(self.stillo_check, False, False, 0)
        people_box.pack_start(self.stillo_note, False, False, 0)

        files_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        files_box.set_margin_top(12)
        files_box.set_margin_bottom(12)
        files_box.set_margin_start(6)
        files_box.set_margin_end(12)
        files_head = Gtk.Box(spacing=8)
        files_label = Gtk.Label(label="History", xalign=0)
        files_label.set_hexpand(True)
        files_label.get_style_context().add_class("heading")
        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        filter_box.get_style_context().add_class("linked")
        filter_group = None
        for key, label in (("all", "All"), ("saved", "Saved"), ("draft", "Drafts")):
            button = Gtk.RadioButton.new_with_label_from_widget(filter_group, label)
            button.set_mode(False)
            filter_group = button
            button.connect("toggled", self.on_file_filter, key)
            filter_box.pack_start(button, False, False, 0)
        files_head.pack_start(files_label, True, True, 0)
        files_head.pack_start(filter_box, False, False, 0)
        self.files_list = Gtk.ListBox()
        self.files_list.set_selection_mode(Gtk.SelectionMode.BROWSE)
        self.files_list.connect("row-selected", self.on_file)
        files_scroll = Gtk.ScrolledWindow()
        files_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        files_scroll.set_min_content_height(120)
        files_scroll.set_vexpand(True)
        files_scroll.add(self.files_list)
        self.preview = Gtk.Image()
        self.preview.set_halign(Gtk.Align.CENTER)
        self.preview.set_valign(Gtk.Align.START)
        self.preview_scroll = Gtk.ScrolledWindow()
        self.preview_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.preview_scroll.set_vexpand(True)
        self.preview_scroll.set_min_content_height(160)
        self.preview_scroll.add(self.preview)
        self.preview_scroll.connect("size-allocate", self.on_preview_size)
        self.report_status = Gtk.Label(label="Select a file to draw its report.", xalign=0)
        self.report_status.set_line_wrap(True)
        self.report_status.get_style_context().add_class("dim")
        self.email_btn = Gtk.Button.new_with_label("Email report")
        self.email_btn.set_sensitive(False)
        self.email_btn.connect("clicked", lambda _button: self.email_report())
        self.share_btn = Gtk.Button.new_with_label("Share")
        self.share_btn.set_sensitive(False)
        self.share_btn.connect("clicked", lambda _button: self.share_report())
        self.enlarge_btn = Gtk.Button.new_with_label("Enlarge")
        self.enlarge_btn.set_sensitive(False)
        self.enlarge_btn.connect("clicked", lambda _button: self.enlarge_report())
        self.delete_btn = Gtk.Button.new_with_label("Delete")
        self.delete_btn.set_sensitive(False)
        self.delete_btn.connect("clicked", lambda _button: self.delete_report())
        report_actions = Gtk.Box(spacing=6)
        report_actions.pack_start(self.email_btn, True, True, 0)
        report_actions.pack_start(self.share_btn, True, True, 0)
        report_actions.pack_start(self.enlarge_btn, True, True, 0)
        report_actions.pack_start(self.delete_btn, True, True, 0)
        self.detail = Gtk.TextView()
        self.detail.set_editable(False)
        self.detail.set_cursor_visible(False)
        self.detail.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.detail.set_left_margin(12)
        self.detail.set_right_margin(12)
        self.detail.set_top_margin(12)
        self.detail.set_bottom_margin(12)
        self.detail.get_style_context().add_class("detail")
        detail_scroll = Gtk.ScrolledWindow()
        detail_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        detail_scroll.set_min_content_height(140)
        detail_scroll.set_vexpand(False)
        detail_scroll.add(self.detail)
        self.detail_exp = Gtk.Expander(label="Email text")
        self.detail_exp.set_expanded(False)
        self.detail_exp.add(detail_scroll)
        history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        history_box.pack_start(files_head, False, False, 0)
        history_box.pack_start(files_scroll, True, True, 0)
        report_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        report_box.pack_start(self.preview_scroll, True, True, 0)
        report_box.pack_start(self.report_status, False, False, 0)
        report_box.pack_start(report_actions, False, False, 0)
        report_box.pack_start(self.detail_exp, False, False, 0)
        self.report_split = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.report_split.get_style_context().add_class("report-split")
        self.report_split.set_wide_handle(True)
        self.report_split.set_position(220)
        self.report_split.connect("size-allocate", self.on_split_size)
        self.report_split.pack1(history_box, False, False)
        self.report_split.pack2(report_box, True, False)
        files_box.pack_start(self.report_split, True, True, 0)

        pane.pack1(people_box, False, False)
        pane.pack2(files_box, True, False)
        self.accounts_pane = pane
        self._build_calculator()
        calc_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bar = Gtk.Box(spacing=12)
        bar.set_margin_top(8)
        bar.set_margin_bottom(4)
        bar.set_margin_start(16)
        bar.set_margin_end(16)
        self.calc_who = Gtk.Label(label="Create an account to save calculations.", xalign=0)
        self.calc_who.set_hexpand(True)
        self.calc_who.get_style_context().add_class("title")
        self.calc_status = Gtk.Label(label="", xalign=1)
        self.calc_status.get_style_context().add_class("dim")
        bar.pack_start(self.calc_who, True, True, 0)
        bar.pack_start(self.calc_status, False, False, 0)
        calc_page.pack_start(bar, False, False, 0)
        calc_page.pack_start(self.calc_view, True, True, 0)
        self.stack = Gtk.Stack()
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        self.stack.add_named(calc_page, "calculator")
        self.stack.add_named(pane, "accounts")
        self.stack.set_visible_child_name("calculator")
        switch = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        switch.get_style_context().add_class("linked")
        self.calc_mode = Gtk.RadioButton.new_with_label_from_widget(None, "Calculator")
        self.calc_mode.set_mode(False)
        self.account_mode = Gtk.RadioButton.new_with_label_from_widget(self.calc_mode, "Accounts")
        self.account_mode.set_mode(False)
        switch.pack_start(self.calc_mode, False, False, 0)
        switch.pack_start(self.account_mode, False, False, 0)
        self.header.pack_end(switch)
        self.calc_mode.connect("toggled", self.on_hub_page, "calculator")
        self.account_mode.connect("toggled", self.on_hub_page, "accounts")
        self.add(self.stack)
        self.reload()
        self.calc_timer = GLib.timeout_add(800, self.poll_calculator)
        self.accounts_timer = GLib.timeout_add(4000, self.auto_refresh_accounts)
        self.connect("map", self.on_map)
        self.connect("destroy", self.on_window_destroy)

    def auto_refresh_accounts(self):
        if self.stack.get_visible_child_name() == "accounts":
            current = accounts_signature()
            if current != getattr(self, "_accounts_sig", None):
                self._accounts_sig = current
                self.reload()
        return True

    def reload(self):
        keep = self._selected_user
        self._accounts_sig = accounts_signature()
        self.people = load_people()
        self.people_list.handler_block_by_func(self.on_person)
        try:
            self.clear_list(self.people_list)
            if not self.people:
                self.people_list.add(self.note_row("No accounts yet."))
                self.people_list.show_all()
                chosen = None
            else:
                chosen = None
                stillo_users = load_stillo_users()
                for person in self.people:
                    row = Gtk.ListBoxRow()
                    row.person = person
                    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                    box.set_margin_top(8)
                    box.set_margin_bottom(8)
                    box.set_margin_start(10)
                    box.set_margin_end(10)
                    name = Gtk.Label(label=person["username"], xalign=0)
                    name.get_style_context().add_class("title")
                    sub = Gtk.Label(label=person_summary(person, stillo_users), xalign=0)
                    sub.get_style_context().add_class("dim")
                    sub.set_line_wrap(True)
                    box.pack_start(name, False, False, 0)
                    box.pack_start(sub, False, False, 0)
                    row.add(box)
                    self.people_list.add(row)
                    if person["id"] == keep:
                        chosen = row
                self.people_list.show_all()
                self.people_list.select_row(chosen or self.people_list.get_row_at_index(0))
        finally:
            self.people_list.handler_unblock_by_func(self.on_person)
        if not self.people:
            self.remove_btn.set_sensitive(False)
            self.reset_btn.set_sensitive(False)
            self._selected_user = None
            self.show_files(None)
            self.request_calculator()
            return
        self.on_person(self.people_list, self.people_list.get_selected_row())

    def current_person(self):
        for person in self.people:
            if person["id"] == self._selected_user:
                return person
        return None

    def update_stillo_control(self, person):
        check = getattr(self, "stillo_check", None)
        note = getattr(self, "stillo_note", None)
        if check is None:
            return
        check.handler_block_by_func(self.on_stillo_toggle)
        try:
            if not person:
                check.set_active(False)
                check.set_sensitive(False)
                check.set_tooltip_text("Select a person.")
            elif person["admin"]:
                check.set_active(True)
                check.set_sensitive(False)
                check.set_tooltip_text("Admins always have access.")
            else:
                check.set_active(stillo_allowed(person["username"]))
                check.set_sensitive(True)
                check.set_tooltip_text("")
        finally:
            check.handler_unblock_by_func(self.on_stillo_toggle)
        if note is not None:
            note.set_text("Admins always have access" if person and person["admin"] else "")

    def on_stillo_toggle(self, check):
        person = self.current_person()
        if not person or person["admin"]:
            return
        try:
            set_stillo_access(person["username"], check.get_active())
        except OSError as exc:
            self.notice("Could not save Ask Stillo access: %s" % exc)
        self.update_stillo_control(person)
        self.reload()

    def on_person(self, _list, row):
        person = getattr(row, "person", None) if row else None
        self._selected_user = person["id"] if person else None
        self.remove_btn.set_sensitive(bool(person) and not person["admin"])
        self.reset_btn.set_sensitive(bool(person))
        self.show_files(person)
        self.update_stillo_control(person)
        self.request_calculator()

    def _build_calculator(self):
        ucm = WebKit2.UserContentManager()
        ucm.register_script_message_handler("fitterhub")
        ucm.connect("script-message-received::fitterhub", self.on_calc_message)
        script = WebKit2.UserScript(
            calculator_bridge_js(),
            WebKit2.UserContentInjectedFrames.ALL_FRAMES,
            WebKit2.UserScriptInjectionTime.START,
            None,
            None,
        )
        ucm.add_script(script)
        data_mgr = WebKit2.WebsiteDataManager.new_ephemeral()
        ctx = WebKit2.WebContext.new_with_website_data_manager(data_mgr)
        try:
            ctx.set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)
        except Exception:
            pass
        settings = WebKit2.Settings()
        settings.set_enable_javascript(True)
        settings.set_enable_html5_local_storage(True)
        settings.set_enable_html5_database(True)
        settings.set_allow_file_access_from_file_urls(True)
        settings.set_allow_universal_access_from_file_urls(True)
        settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
        settings.set_enable_fullscreen(False)
        try:
            settings.set_enable_page_cache(False)
        except Exception:
            pass
        self.calc_view = WebKit2.WebView(
            web_context=ctx,
            user_content_manager=ucm,
            settings=settings,
        )
        color = Gdk.RGBA()
        color.parse("#14110f")
        self.calc_view.set_background_color(color)
        self.calc_view.set_hexpand(True)
        self.calc_view.set_vexpand(True)
        self.calc_view.connect("load-changed", self.on_calc_load)
        self.calc_view.connect("load-failed", self.on_calc_fail)
        self._calc_load_started = False

    def on_map(self, *_args):
        if not self._calc_load_started:
            self._calc_load_started = True
            self.calc_view.load_uri(PAGE.resolve().as_uri())
        if self.stack.get_visible_child_name() == "calculator":
            self.calc_view.grab_focus()

    def on_hub_page(self, button, name):
        if not button.get_active():
            return
        self.stack.set_visible_child_name(name)
        if name == "calculator":
            self.calc_view.grab_focus()
            return
        self.flush_then(self.refresh_history_if_dirty)

    def refresh_history_if_dirty(self):
        if not self.history_dirty:
            return
        if self.stack.get_visible_child_name() != "accounts":
            return
        self.history_dirty = False
        self.reload()

    def on_refresh(self):
        def after():
            self.calc_user_id = None
            self.calc_page_owner = None
            self.calc_baseline = None
            self.calc_paused = True
            self.reload()
        self.flush_then(after)

    def request_calculator(self):
        person = self.current_person()
        if not person:
            self.calc_who.set_text("Create an account to save calculations.")
            self.calc_status.set_text("")
            self.calc_paused = True
            self.calc_user_id = None
            self.calc_page_owner = None
            self.calc_baseline = None
            return
        self.calc_who.set_text("Working as %s." % person["username"])
        if person["id"] == self.calc_user_id and self.calc_page_owner == person["id"]:
            return
        user_id = person["id"]
        self.flush_then(lambda user_id=user_id: self.inject_if_current(user_id))

    def inject_if_current(self, user_id):
        person = self.current_person()
        if not person or person["id"] != user_id:
            return
        if self.calc_user_id == user_id and self.calc_page_owner == user_id:
            return
        self.inject_calculator(user_id)

    def flush_then(self, afterwards):
        """Save the open page, then run afterwards. A newer switch drops this one."""
        self.calc_generation += 1
        generation = self.calc_generation
        owner = self.calc_page_owner
        self.calc_paused = True

        def finish():
            if generation != self.calc_generation:
                return
            afterwards()
            self.resume_calculator(generation)

        if not owner or not self._page_loaded:
            finish()
            return

        def on_js(view, result, _data):
            if generation != self.calc_generation:
                return
            try:
                text = js_text(view, result)
                changed = write_calculator_snapshot(owner, text)
            except Exception:
                self.calc_status.set_text("Could not save these calculations.")
                finish()
                return
            if changed is True:
                self.history_dirty = True
            if changed is not None:
                self.calc_baseline = text
            finish()

        try:
            self.calc_view.run_javascript("window.fcHubFlush()", None, on_js, None)
        except Exception:
            finish()

    def resume_calculator(self, generation):
        if generation != self.calc_generation or self._calc_pending:
            return
        if self.calc_page_owner and self.calc_user_id == self.calc_page_owner and self._page_loaded:
            self.calc_paused = False

    def inject_calculator(self, user_id):
        generation = self.calc_generation
        self.calc_page_owner = None
        self.calc_user_id = None
        self.calc_baseline = None
        self.calc_paused = True
        if not self._page_loaded:
            self._calc_pending = (generation, user_id)
            return
        try:
            conn = accounts.connect()
            try:
                state = accounts._dump_state(conn, user_id)
            finally:
                conn.close()
        except Exception:
            self.calc_status.set_text("Could not open this person's calculations.")
            return
        script = calculator_inject_script(state)
        try:
            self.calc_view.run_javascript(script, None, self.on_calc_inject, (generation, user_id))
        except Exception:
            self.calc_status.set_text("Could not open this person's calculations.")

    def on_calc_inject(self, view, result, data):
        generation, user_id = data
        if generation != self.calc_generation:
            return
        person = self.current_person()
        if not person or person["id"] != user_id:
            return
        try:
            info = json.loads(js_text(view, result))
        except Exception:
            self.calc_status.set_text("Could not open this person's calculations.")
            return
        if not isinstance(info, dict) or info.get("err") or not isinstance(info.get("read"), str):
            self.calc_status.set_text("Could not open this person's calculations.")
            return
        self.calc_baseline = info["read"]
        self.calc_page_owner = user_id
        self.calc_user_id = user_id
        self.calc_paused = False
        self.calc_status.set_text("Saved")

    def on_calc_load(self, _view, event):
        if event != WebKit2.LoadEvent.FINISHED:
            return
        self._page_loaded = True
        pending = self._calc_pending
        self._calc_pending = None
        if pending and pending[0] == self.calc_generation:
            self.inject_calculator(pending[1])
            return
        self.request_calculator()

    def on_calc_fail(self, _view, _event, _uri, _error):
        self.calc_paused = True
        self.calc_status.set_text("The calculator did not open.")
        return True

    def poll_calculator(self):
        # Read storage only. autosave stamps the current time and would rewrite every poll.
        if (
            self.calc_paused
            or self.calc_poll_busy
            or not self._page_loaded
            or self.calc_user_id is None
            or self.calc_page_owner != self.calc_user_id
        ):
            return True
        generation = self.calc_generation
        user_id = self.calc_user_id
        self.calc_poll_busy = True
        try:
            self.calc_view.run_javascript(
                "window.fcHubRead()", None, self.on_calc_poll, (generation, user_id)
            )
        except Exception:
            self.calc_poll_busy = False
        return True

    def on_calc_poll(self, view, result, data):
        self.calc_poll_busy = False
        generation, user_id = data
        if (
            self.calc_paused
            or generation != self.calc_generation
            or user_id != self.calc_user_id
            or user_id != self.calc_page_owner
        ):
            return
        try:
            text = js_text(view, result)
        except Exception:
            return
        if text == self.calc_baseline:
            return
        try:
            changed = write_calculator_snapshot(user_id, text)
        except Exception:
            self.calc_status.set_text("Could not save these calculations.")
            return
        if changed is None:
            return
        self.calc_baseline = text
        if changed:
            self.history_dirty = True
            self.calc_status.set_text("Saved")

    def on_calc_message(self, _manager, result):
        try:
            msg = json.loads(result.get_js_value().to_string())
        except Exception:
            return
        if not isinstance(msg, dict):
            return
        op = msg.get("op")
        try:
            if op == "save":
                path, _raw = save_report_png(msg.get("dataUrl"), msg.get("filename"))
                self.calc_status.set_text("Saved %s" % path.name)
            elif op == "email":
                path = open_calculator_email(
                    msg.get("dataUrl"),
                    msg.get("filename"),
                    msg.get("subject"),
                    msg.get("body"),
                )
                self.calc_status.set_text("Opening email with %s" % path.name)
            elif op == "emailText":
                subject = msg.get("subject") or "FitterCalcs report"
                body = msg.get("body") or ""
                if shutil.which("xdg-email"):
                    subprocess.Popen(
                        ["xdg-email", "--subject", subject, "--body", body],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    subprocess.Popen(
                        ["xdg-open", "mailto:?subject=%s" % subject],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                self.calc_status.set_text("Opening email")
            elif op == "toast":
                self.calc_status.set_text(str(msg.get("msg") or ""))
            elif op == "fullscreen":
                if msg.get("on"):
                    self.fullscreen()
                else:
                    self.unfullscreen()
            elif op == "share":
                kind = str(msg.get("kind") or "")
                job_id = str(msg.get("id") or "")
                self.flush_then(lambda kind=kind, job_id=job_id: self.share_from_calculator(kind, job_id))
            elif op == "sync":
                self.flush_then(self.refresh_history_if_dirty)
        except Exception as exc:
            self.calc_status.set_text(str(exc))

    def share_from_calculator(self, kind, job_id):
        self.history_dirty = False
        self.reload()
        user_id = self.calc_page_owner or self.calc_user_id
        person = None
        item = None
        for candidate in self.people:
            if candidate["id"] != user_id:
                continue
            person = candidate
            for found in candidate["files"]:
                if not found["draft"] and found["kind"] == kind and str(found["job_id"]) == job_id:
                    item = found
                    break
        if not person or not item:
            self.notice("Save the report before sharing it.")
            return
        self.share_report(person=person, item=item)

    def on_window_destroy(self, *_args):
        if self.calc_timer:
            GLib.source_remove(self.calc_timer)
            self.calc_timer = 0
        owner = self.calc_page_owner
        self.calc_paused = True
        self.calc_generation += 1
        if not owner or not self._page_loaded:
            return
        done = {"ok": False}

        def finish(view, result, _data):
            try:
                text = js_text(view, result)
                write_calculator_snapshot(owner, text)
            except Exception:
                pass
            done["ok"] = True

        try:
            self.calc_view.run_javascript("window.fcHubFlush()", None, finish, None)
        except Exception:
            return
        context = GLib.MainContext.default()
        deadline = time.monotonic() + 0.4
        while not done["ok"] and time.monotonic() < deadline:
            context.iteration(False)

    def on_file_filter(self, button, key):
        if not button.get_active() or key == self.file_filter:
            return
        self.file_filter = key
        self.show_files(self.current_person())

    def show_files(self, person):
        keep = self._selected_file
        visible = [item for item in person["files"] if file_matches(item, self.file_filter)] if person else []
        pick = None
        self.files_list.handler_block_by_func(self.on_file)
        try:
            self.clear_list(self.files_list)
            if not person:
                self.files_list.add(self.note_row("Select a person."))
                self._selected_file = None
                self.clear_report()
                self.set_detail("")
                self.report_status.set_text("Select a file to draw its report.")
                self.files_list.show_all()
                return
            if not visible:
                if self.file_filter == "saved":
                    note = "No saved jobs."
                elif self.file_filter == "draft":
                    note = "No drafts."
                else:
                    note = "No jobs for this person."
                self.files_list.add(self.note_row(note))
                self._selected_file = None
                self.clear_report()
                self.set_detail("")
                self.report_status.set_text(note)
                self.files_list.show_all()
                return
            chosen = None
            first = None
            for item in visible:
                row = Gtk.ListBoxRow()
                row.item = item
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                box.set_margin_top(8)
                box.set_margin_bottom(8)
                box.set_margin_start(10)
                box.set_margin_end(10)
                title = Gtk.Label(label=item["title"], xalign=0)
                title.set_line_wrap(True)
                title.get_style_context().add_class("title")
                sub = Gtk.Label(label=file_summary(item), xalign=0)
                sub.get_style_context().add_class("dim")
                box.pack_start(title, False, False, 0)
                box.pack_start(sub, False, False, 0)
                row.add(box)
                self.files_list.add(row)
                if first is None:
                    first = row
                if item is keep:
                    chosen = row
            self.files_list.show_all()
            if chosen is not None:
                self.files_list.select_row(chosen)
            else:
                pick = first
        finally:
            self.files_list.handler_unblock_by_func(self.on_file)
        if pick is not None:
            self.files_list.select_row(pick)

    def on_file(self, _list, row):
        item = getattr(row, "item", None) if row else None
        self._selected_file = item
        self.set_detail(item["detail"] if item else "")
        self.clear_report()
        if not item:
            return
        self.report_status.set_text("Drawing the report…")
        token = item
        self.reports.request(item["kind"], item["state"], lambda data, chosen=token: self.on_report(chosen, data))

    def on_split_size(self, widget, alloc):
        if self._split_ready or alloc.height < 320:
            return
        self._split_ready = True
        widget.set_position(min(220, max(140, alloc.height // 4)))

    def sync_report_buttons(self):
        item = self._selected_file
        self.delete_btn.set_sensitive(item is not None)
        self.share_btn.set_sensitive(bool(item) and not item.get("draft"))
        self.enlarge_btn.set_sensitive(self.report_full is not None)

    def on_preview_size(self, _widget, alloc):
        if self.report_full is None or alloc.width < 80:
            return
        width = min(self.report_full.get_width(), max(240, alloc.width - 12))
        if abs(width - self._preview_width) < 8:
            return
        self.fit_preview(width)

    def fit_preview(self, width=None):
        pix = self.report_full
        if pix is None:
            return
        if width is None:
            width = min(pix.get_width(), max(240, self.preview_scroll.get_allocated_width() - 12))
        self._preview_width = width
        if pix.get_width() == width:
            shown = pix
        else:
            height = max(1, int(pix.get_height() * width / pix.get_width()))
            shown = pix.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
        self.preview.set_from_pixbuf(shown)

    def close_enlarge(self):
        window = self.enlarge_window
        self.enlarge_window = None
        if window is not None:
            window.destroy()

    def on_enlarge_closed(self, window):
        if self.enlarge_window is window:
            self.enlarge_window = None

    def enlarge_report(self):
        if self.report_full is None:
            self.notice("Draw a report first.")
            return
        if self.enlarge_window is not None:
            self.enlarge_window.present()
            return
        window = theme(Gtk.Window(title=self.report_name or "Report"))
        window.set_transient_for(self)
        screen = self.get_screen()
        window.set_default_size(
            min(screen.get_width() - 80, self.report_full.get_width() + 40),
            min(screen.get_height() - 80, 900),
        )
        scroll = Gtk.ScrolledWindow()
        image = Gtk.Image()
        image.set_halign(Gtk.Align.CENTER)
        image.set_valign(Gtk.Align.START)
        image.set_from_pixbuf(self.report_full)
        scroll.add(image)
        window.add(scroll)
        window.connect("destroy", self.on_enlarge_closed)
        self.enlarge_window = window
        window.show_all()

    def on_forget_job(self, _view, _result, _data):
        return

    def delete_report(self):
        item = self._selected_file
        person = self.current_person()
        if not item or not person:
            return
        kind = "draft" if item["draft"] else "saved job"
        dialog = theme(Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text="Delete this report?",
        ))
        dialog.format_secondary_text(
            "This removes the %s \"%s\" from this server." % (kind, item["title"])
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Delete", Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        picture = self.report_png
        try:
            delete_file(person["id"], item)
        except ValueError as exc:
            self.notice(str(exc))
            return
        remove_saved_picture(picture)
        self._selected_file = None
        self.reload()
        if self.calc_page_owner == person["id"] and self._page_loaded and self.calc_view:
            kind_name = str(item.get("kind") or "")
            gone_id = "" if item.get("draft") else str(item.get("job_id") or "")
            script = "if (window.fcForgetJob) window.fcForgetJob(%s, %s);" % (
                json.dumps(kind_name),
                json.dumps(gone_id),
            )
            try:
                self.calc_view.run_javascript(script, None, self.on_forget_job, None)
            except Exception:
                pass

    def clear_report(self):
        self.close_enlarge()
        self.report_png = None
        self.report_full = None
        self.report_subject = ""
        self.report_body = ""
        self.report_name = ""
        self.email_btn.set_sensitive(False)
        self.share_btn.set_sensitive(False)
        self._preview_width = 0
        self.preview.clear()
        self.sync_report_buttons()

    def on_report(self, item, data):
        if item is not self._selected_file:
            return
        if data.get("error"):
            self.report_status.set_text(data["error"])
            return
        try:
            path, raw = save_report_png(data.get("png"), data.get("fname"))
        except ValueError as exc:
            self.report_status.set_text(str(exc))
            return
        loader = GdkPixbuf.PixbufLoader.new_with_type("png")
        loader.write(raw)
        loader.close()
        self.report_full = loader.get_pixbuf()
        self.report_png = path
        self.report_subject = data.get("subject") or "FitterCalcs report"
        self.report_body = data.get("body") or ""
        self.report_name = path.name
        self.email_btn.set_sensitive(True)
        self.fit_preview()
        self.sync_report_buttons()
        self.report_status.set_text("Report ready. Drag the divider, or enlarge this picture.")
        if self.report_body:
            self.set_detail(self.report_body)

    def create_account(self):
        dialog = theme(Gtk.Dialog(title="Create account", transient_for=self, modal=True))
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Create", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        name = Gtk.Entry()
        name.set_placeholder_text("Name")
        email = Gtk.Entry()
        email.set_placeholder_text("Email, optional")
        password = Gtk.Entry()
        password.set_visibility(False)
        password.set_placeholder_text("Password")
        confirm = Gtk.Entry()
        confirm.set_visibility(False)
        confirm.set_placeholder_text("Password again")
        stillo = Gtk.CheckButton(label="Allow Ask Stillo")
        error = Gtk.Label(label="", xalign=0)
        error.get_style_context().add_class("dim")
        for widget in (name, email, password, confirm, stillo, error):
            box.pack_start(widget, False, False, 0)
        dialog.show_all()
        dialog.set_default_size(360, 260)
        while True:
            if dialog.run() != Gtk.ResponseType.OK:
                break
            try:
                created = create_person(
                    name.get_text(), password.get_text(), email.get_text(), confirm.get_text(),
                    stillo.get_active()
                )
            except ValueError as exc:
                error.set_text(str(exc))
                continue
            self._selected_user = created["id"]
            dialog.destroy()
            self.reload()
            return
        dialog.destroy()

    def remove_account(self):
        person = self.current_person()
        if not person:
            return
        if person["admin"]:
            self.notice("The first account can't be removed.")
            return
        dialog = theme(Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text="Remove %s?" % person["username"],
        ))
        dialog.format_secondary_text(
            "Their saved pump, hydro, tank, fan, and flow jobs will be deleted from this server, "
            "and their Ask Stillo access will be removed."
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Remove", Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        try:
            delete_person(person["id"])
        except ValueError as exc:
            self.notice(str(exc))
            return
        self._selected_user = None
        self.reload()

    def reset_password_dialog(self):
        person = self.current_person()
        if not person:
            return
        dialog = theme(Gtk.Dialog(title="Reset password", transient_for=self, modal=True))
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        note = Gtk.Label(
            label="%s will need to sign in again with the new password." % person["username"],
            xalign=0,
        )
        note.set_line_wrap(True)
        note.set_max_width_chars(42)
        password = Gtk.Entry()
        password.set_visibility(False)
        password.set_placeholder_text("New password")
        confirm = Gtk.Entry()
        confirm.set_visibility(False)
        confirm.set_placeholder_text("New password again")
        error = Gtk.Label(label="", xalign=0)
        error.set_line_wrap(True)
        error.get_style_context().add_class("dim")
        for widget in (note, password, confirm, error):
            box.pack_start(widget, False, False, 0)
        dialog.show_all()
        dialog.set_default_size(380, 180)
        while True:
            if dialog.run() != Gtk.ResponseType.OK:
                break
            try:
                reset_person(person["id"], password.get_text(), confirm.get_text())
            except ValueError as exc:
                error.set_text(str(exc))
                continue
            dialog.destroy()
            self.notice("Password updated. %s needs to sign in again." % person["username"])
            return
        dialog.destroy()

    def share_report(self, person=None, item=None):
        if item is None:
            item = self._selected_file
        if person is None:
            person = self.current_person()
        if not item or not person:
            return
        if item.get("draft"):
            self.notice("Save the report before sharing it.")
            return
        others = [other for other in self.people if other["id"] != person["id"]]
        if not others:
            self.notice("Add another account before sharing a report.")
            return
        dialog = theme(Gtk.Dialog(title="Share report", transient_for=self, modal=True))
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Share", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        note = Gtk.Label(
            label='Send a copy of "' + item["title"] + '" to another account. It also stays with '
            + person["username"] + ".",
            xalign=0,
        )
        note.set_line_wrap(True)
        note.set_max_width_chars(42)
        people = Gtk.ListBox()
        people.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for other in others:
            row = Gtk.ListBoxRow()
            row.share_name = other["username"]
            label = Gtk.Label(label=other["username"], xalign=0)
            label.set_margin_top(8)
            label.set_margin_bottom(8)
            label.set_margin_start(10)
            label.set_margin_end(10)
            row.add(label)
            people.add(row)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(min(220, 48 * len(others)))
        scroll.add(people)
        error = Gtk.Label(label="", xalign=0)
        error.set_line_wrap(True)
        error.get_style_context().add_class("dim")
        box.pack_start(note, False, False, 0)
        box.pack_start(scroll, True, True, 0)
        box.pack_start(error, False, False, 0)
        dialog.show_all()
        dialog.set_default_size(420, 280)
        first = people.get_row_at_index(0)
        if first is not None:
            people.select_row(first)
        while True:
            if dialog.run() != Gtk.ResponseType.OK:
                break
            chosen = people.get_selected_row()
            if chosen is None:
                error.set_text("Choose a person.")
                continue
            try:
                shared = accounts.share_job(
                    person["id"], item["kind"], item["job_id"], chosen.share_name
                )
            except ValueError as exc:
                error.set_text(str(exc))
                continue
            dialog.destroy()
            self.notice(
                "Shared with %s. They see it the next time their app syncs."
                % shared["username"]
            )
            return
        dialog.destroy()

    def email_report(self):
        if not self.report_png:
            self.notice("Draw a report first.")
            return
        dialog = theme(Gtk.Dialog(title="Email report", transient_for=self, modal=True))
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Email", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        note = Gtk.Label(
            label="Send this report picture to someone. Your email app opens with it attached.",
            xalign=0,
        )
        note.set_line_wrap(True)
        note.set_max_width_chars(42)
        address = Gtk.ComboBoxText.new_with_entry()
        for person in self.people:
            if person.get("email"):
                address.append_text("%s <%s>" % (person["username"], person["email"]))
        address.get_child().set_placeholder_text("name@example.com")
        error = Gtk.Label(label="", xalign=0)
        error.get_style_context().add_class("dim")
        box.pack_start(note, False, False, 0)
        box.pack_start(address, False, False, 0)
        box.pack_start(error, False, False, 0)
        dialog.show_all()
        dialog.set_default_size(420, 160)
        while True:
            if dialog.run() != Gtk.ResponseType.OK:
                break
            typed = address.get_active_text().strip()
            if "<" in typed and typed.endswith(">"):
                typed = typed.rsplit("<", 1)[1][:-1].strip()
            try:
                message = send_report(self.report_png, self.report_subject, self.report_body, typed)
            except ValueError as exc:
                error.set_text(str(exc))
                continue
            dialog.destroy()
            self.report_status.set_text(message)
            return
        dialog.destroy()

    def notice(self, text):
        dialog = theme(Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=text,
        ))
        dialog.run()
        dialog.destroy()

    def set_detail(self, text):
        buf = self.detail.get_buffer()
        buf.set_text(text or "")

    def clear_list(self, box):
        for child in box.get_children():
            box.remove(child)

    def note_row(self, text):
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        label = Gtk.Label(label=text, xalign=0)
        label.set_margin_top(8)
        label.set_margin_bottom(8)
        label.set_margin_start(10)
        label.set_margin_end(10)
        label.get_style_context().add_class("dim")
        row.add(label)
        return row


def check():
    people = load_people()
    print("people %d" % len(people))
    for person in people:
        saved = sum(1 for item in person["files"] if not item["draft"])
        drafts = sum(1 for item in person["files"] if item["draft"])
        print("user %s admin=%s saved=%d drafts=%d" % (
            person["username"], person["admin"], saved, drafts
        ))
        for item in person["files"]:
            print("  %s %s %s" % (
                "draft" if item["draft"] else "saved",
                item["kind"],
                item["title"],
            ))
    return 0 if people else 1


def main():
    if "--check" in sys.argv:
        raise SystemExit(check())
    win = AdminWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    if win.stack.get_visible_child_name() == "calculator":
        win.calc_view.grab_focus()
    Gtk.main()


if __name__ == "__main__":
    main()
