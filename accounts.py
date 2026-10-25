"""Accounts and per-person job history for the FitterCalcs server."""

import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit

DB = Path(os.environ.get("FITTERCALCS_DB") or (Path.home() / ".local/share/fittercalcs/accounts.db"))
KINDS = ("pump", "hydro", "tank")
MAX_BODY = 1_000_000
ROUNDS = 210_000
SESSION_SECONDS = 60 * 24 * 3600
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,31}$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_fails = {}
_regs = {}


class Result:
    def __init__(self, status, body, session=None, clear_session=False):
        self.status = status
        self.body = body
        self.session = session
        self.clear_session = clear_session


def init_db():
    DB.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    conn = connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS jobs (
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                job_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, kind, job_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS drafts (
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, kind),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()
    finally:
        conn.close()
    try:
        os.chmod(DB, 0o600)
    except OSError:
        pass


def connect():
    DB.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ok(body, session=None):
    return Result(200, body, session=session)


def _err(status, message):
    return Result(status, {"error": message})


def _too_many(ip):
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < 600]
    _fails[ip] = recent
    return len(recent) >= 8


def _note_fail(ip):
    _fails.setdefault(ip, []).append(time.time())


def _clear_fails(ip):
    _fails.pop(ip, None)


def _too_many_reg(ip):
    now = time.time()
    recent = [t for t in _regs.get(ip, []) if now - t < 600]
    _regs[ip] = recent
    return len(recent) >= 8


def _note_reg(ip):
    _regs.setdefault(ip, []).append(time.time())


def _clean_username(value):
    name = str(value or "").strip()
    if not NAME_RE.match(name):
        raise ValueError("Use 2–32 letters or numbers for the name.")
    return name


def _clean_password(value):
    password = str(value or "")
    if len(password) < 8:
        raise ValueError("Use at least 8 characters for the password.")
    if len(password) > 200:
        raise ValueError("That password is too long.")
    return password


def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ROUNDS)


def _as_ms(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = int(value)
    if number < 0 or number > 9_000_000_000_000:
        return None
    return number


def _user_count(conn):
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def _public_user(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "admin": bool(row["is_admin"]),
    }


def _insert_user(conn, username, password, admin):
    name = _clean_username(username)
    password = _clean_password(password)
    if _user_count(conn) >= 100:
        raise ValueError("The server already has 100 accounts.")
    salt = secrets.token_bytes(16)
    digest = _hash_password(password, salt)
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, salt, is_admin, created_at) VALUES (?,?,?,?,?)",
            (name, digest.hex(), salt.hex(), 1 if admin else 0, int(time.time())),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError("That name is already in use.") from exc
    return {"id": cur.lastrowid, "username": name, "admin": bool(admin)}


def _new_session(conn, user_id):
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?,?,?)",
        (digest, user_id, int(time.time()) + SESSION_SECONDS),
    )
    return token


def _user_for_token(token):
    if not token or len(token) > 200:
        return None
    digest = hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()
    conn = connect()
    try:
        row = conn.execute(
            """SELECT users.id, users.username, users.is_admin, sessions.expires_at
               FROM sessions JOIN users ON users.id = sessions.user_id
               WHERE sessions.token_hash = ?""",
            (digest,),
        ).fetchone()
        if not row:
            return None
        if row["expires_at"] < time.time():
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (digest,))
            conn.commit()
            return None
        return {"id": row["id"], "username": row["username"], "admin": bool(row["is_admin"])}
    finally:
        conn.close()


def _check_password(username, password):
    name = str(username or "").strip()
    password = str(password or "")
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, salt, is_admin FROM users WHERE username = ? COLLATE NOCASE",
            (name,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        salt = bytes.fromhex(row["salt"])
        expect = bytes.fromhex(row["password_hash"])
    except ValueError:
        return None
    got = _hash_password(password, salt)
    if not secrets.compare_digest(got, expect):
        return None
    return {"id": row["id"], "username": row["username"], "admin": bool(row["is_admin"])}


def _dump_state(conn, user_id):
    jobs = {}
    known = {}
    for kind in KINDS:
        rows = conn.execute(
            "SELECT payload, updated_at FROM jobs WHERE user_id = ? AND kind = ? ORDER BY updated_at DESC",
            (user_id, kind),
        ).fetchall()
        items = []
        for row in rows:
            try:
                rec = json.loads(row["payload"])
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                items.append(rec)
        jobs[kind] = items
        known[kind] = [str(rec.get("id")) for rec in items if rec.get("id")]
    drafts = {}
    for kind in KINDS:
        row = conn.execute(
            "SELECT payload FROM drafts WHERE user_id = ? AND kind = ?",
            (user_id, kind),
        ).fetchone()
        draft = None
        if row:
            try:
                parsed = json.loads(row["payload"])
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                draft = parsed
        drafts[kind] = draft
    return {"jobs": jobs, "drafts": drafts, "known": known}


def _sync(user_id, data):
    jobs_in = data.get("jobs") if isinstance(data.get("jobs"), dict) else {}
    known_in = data.get("known") if isinstance(data.get("known"), dict) else {}
    drafts_in = data.get("drafts") if isinstance(data.get("drafts"), dict) else {}
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        for kind in KINDS:
            incoming = jobs_in.get(kind)
            if not isinstance(incoming, list):
                incoming = []
            seen = set()
            for rec in incoming[:80]:
                if not isinstance(rec, dict):
                    continue
                job_id = str(rec.get("id") or "")
                if not ID_RE.match(job_id):
                    continue
                updated = _as_ms(rec.get("updated"))
                if updated is None:
                    updated = int(time.time() * 1000)
                stored = dict(rec)
                stored["id"] = job_id
                stored["updated"] = updated
                blob = json.dumps(stored, separators=(",", ":"), ensure_ascii=False)
                if len(blob) > 200_000:
                    continue
                row = conn.execute(
                    "SELECT updated_at FROM jobs WHERE user_id = ? AND kind = ? AND job_id = ?",
                    (user_id, kind, job_id),
                ).fetchone()
                seen.add(job_id)
                if row and row["updated_at"] > updated:
                    continue
                conn.execute(
                    """INSERT INTO jobs (user_id, kind, job_id, payload, updated_at)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(user_id, kind, job_id) DO UPDATE SET
                         payload = excluded.payload,
                         updated_at = excluded.updated_at""",
                    (user_id, kind, job_id, blob, updated),
                )
            known = known_in.get(kind)
            if isinstance(known, list):
                for item in known[:200]:
                    job_id = str(item or "")
                    if ID_RE.match(job_id) and job_id not in seen:
                        conn.execute(
                            "DELETE FROM jobs WHERE user_id = ? AND kind = ? AND job_id = ?",
                            (user_id, kind, job_id),
                        )
            draft = drafts_in.get(kind)
            if isinstance(draft, dict):
                updated = _as_ms(draft.get("updated"))
                if updated is None:
                    continue
                blob = json.dumps(draft, separators=(",", ":"), ensure_ascii=False)
                if len(blob) > 200_000:
                    continue
                row = conn.execute(
                    "SELECT updated_at FROM drafts WHERE user_id = ? AND kind = ?",
                    (user_id, kind),
                ).fetchone()
                if row and row["updated_at"] > updated:
                    continue
                conn.execute(
                    """INSERT INTO drafts (user_id, kind, payload, updated_at)
                       VALUES (?,?,?,?)
                       ON CONFLICT(user_id, kind) DO UPDATE SET
                         payload = excluded.payload,
                         updated_at = excluded.updated_at""",
                    (user_id, kind, blob, updated),
                )
        state = _dump_state(conn, user_id)
        conn.commit()
        return state
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _origin_ok(origin, host):
    if not origin or origin == "null":
        return not origin
    if not host:
        return False
    location = urlsplit(origin)
    return location.netloc == host


def handle(method, path, data, token, ip, origin="", host=""):
    init_db()
    if method in ("POST", "DELETE") and not _origin_ok(origin, host):
        return _err(403, "Blocked.")
    user = _user_for_token(token)
    if path == "/api/setup" and method == "GET":
        conn = connect()
        try:
            needed = _user_count(conn) == 0
        finally:
            conn.close()
        return _ok({"needed": needed})
    if path == "/api/setup" and method == "POST":
        if _too_many(ip):
            return _err(429, "Too many attempts. Wait a few minutes.")
        conn = connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if _user_count(conn):
                conn.rollback()
                return _err(409, "An account already exists. Sign in.")
            try:
                created = _insert_user(conn, data.get("username"), data.get("password"), True)
            except ValueError as exc:
                conn.rollback()
                _note_fail(ip)
                return _err(400, str(exc))
            session = _new_session(conn, created["id"])
            conn.commit()
        finally:
            conn.close()
        _clear_fails(ip)
        return _ok(
            {"username": created["username"], "admin": True},
            session=session,
        )
    if path == "/api/login" and method == "POST":
        if _too_many(ip):
            return _err(429, "Too many attempts. Wait a few minutes.")
        found = _check_password(data.get("username"), data.get("password"))
        if not found:
            _note_fail(ip)
            return _err(401, "Name or password is wrong.")
        conn = connect()
        try:
            session = _new_session(conn, found["id"])
            conn.commit()
        finally:
            conn.close()
        _clear_fails(ip)
        return _ok(
            {"username": found["username"], "admin": found["admin"]},
            session=session,
        )
    if path == "/api/register" and method == "POST":
        if _too_many_reg(ip):
            return _err(429, "Too many new accounts. Wait a few minutes.")
        _note_reg(ip)
        conn = connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if _user_count(conn) == 0:
                conn.rollback()
                return _err(409, "Create the first account first.")
            try:
                created = _insert_user(conn, data.get("username"), data.get("password"), False)
            except ValueError as exc:
                conn.rollback()
                return _err(400, str(exc))
            session = _new_session(conn, created["id"])
            conn.commit()
        finally:
            conn.close()
        return _ok(
            {"username": created["username"], "admin": False},
            session=session,
        )
    if path == "/api/logout" and method == "POST":
        if token:
            digest = hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()
            conn = connect()
            try:
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (digest,))
                conn.commit()
            finally:
                conn.close()
        return Result(200, {"ok": True}, clear_session=True)
    if path == "/api/me" and method == "GET":
        if not user:
            return _err(401, "Sign in.")
        return _ok({"username": user["username"], "admin": user["admin"]})
    if path == "/api/users" and method == "GET":
        if not user:
            return _err(401, "Sign in.")
        if not user["admin"]:
            return _err(403, "Only the first account can add people.")
        conn = connect()
        try:
            rows = conn.execute(
                "SELECT id, username, is_admin FROM users ORDER BY username COLLATE NOCASE"
            ).fetchall()
        finally:
            conn.close()
        return _ok({"users": [_public_user(row) for row in rows]})
    if path == "/api/users" and method == "POST":
        if not user:
            return _err(401, "Sign in.")
        if not user["admin"]:
            return _err(403, "Only the first account can add people.")
        conn = connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                created = _insert_user(conn, data.get("username"), data.get("password"), False)
            except ValueError as exc:
                conn.rollback()
                return _err(400, str(exc))
            conn.commit()
        finally:
            conn.close()
        return _ok(created)
    if path.startswith("/api/users/") and method == "DELETE":
        if not user:
            return _err(401, "Sign in.")
        if not user["admin"]:
            return _err(403, "Only the first account can remove people.")
        tail = path[len("/api/users/"):]
        if not tail.isdigit():
            return _err(404, "No such account.")
        target = int(tail)
        if target == user["id"]:
            return _err(400, "Sign in as someone else before removing your own account.")
        conn = connect()
        try:
            row = conn.execute("SELECT id, is_admin FROM users WHERE id = ?", (target,)).fetchone()
            if not row:
                return _err(404, "No such account.")
            if row["is_admin"]:
                return _err(400, "That account can't be removed.")
            conn.execute("DELETE FROM users WHERE id = ?", (target,))
            conn.commit()
        finally:
            conn.close()
        return _ok({"ok": True})
    if path == "/api/sync" and method == "POST":
        if not user:
            return _err(401, "Sign in.")
        try:
            state = _sync(user["id"], data if isinstance(data, dict) else {})
        except sqlite3.Error:
            return _err(500, "The server could not save that job.")
        return _ok(state)
    return _err(404, "Not found.")
