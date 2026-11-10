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
KINDS = ("pump", "hydro", "tank", "fan", "flow")
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
            CREATE TABLE IF NOT EXISTS removed (
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                job_id TEXT NOT NULL,
                removed_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, kind, job_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if "email" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        removed_cols = {row[1] for row in conn.execute("PRAGMA table_info(removed)")}
        if "fingerprint" not in removed_cols:
            conn.execute(
                "ALTER TABLE removed ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''"
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


REG_WINDOW = 600


def reg_limit() -> int:
    try:
        value = int(os.environ.get("FITTERCALCS_REG_LIMIT") or 20)
    except ValueError:
        value = 20
    return max(1, value)


def _reg_recent(ip):
    now = time.time()
    recent = [t for t in _regs.get(ip, []) if now - t < REG_WINDOW]
    _regs[ip] = recent
    return recent


def _too_many_reg(ip):
    return len(_reg_recent(ip)) >= reg_limit()


def _reg_wait(ip):
    recent = _reg_recent(ip)
    if not recent:
        return 0
    return max(0, int(REG_WINDOW - (time.time() - min(recent))) + 1)


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


def user_for_session(token):
    """Public session lookup for the Ask assistant."""
    return _user_for_token(token)


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


def reset_password(user_id, password):
    """Set a new password and drop every session for that person."""
    password = _clean_password(password)
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError("No such account.") from None
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            raise ValueError("No such account.")
        salt = secrets.token_bytes(16)
        digest = _hash_password(password, salt)
        conn.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
            (digest.hex(), salt.hex(), row["id"]),
        )
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
        conn.commit()
        return row["username"]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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


def _removed_blocks(conn, user_id, kind, job_id, updated, fingerprint=""):
    """True when this upload is the copy that was deleted.

    A later edit of that same id has a different body and is kept.
    An unchanged copy stays deleted even when its timestamp moved forward.
    """
    row = conn.execute(
        "SELECT removed_at, fingerprint FROM removed WHERE user_id = ? AND kind = ? AND job_id = ?",
        (user_id, kind, job_id),
    ).fetchone()
    if not row:
        return False
    stored = row["fingerprint"] or ""
    if stored and fingerprint and stored == fingerprint:
        return True
    # The draft slot is one row per kind. A different sheet must still save.
    if job_id == "" and stored and fingerprint and stored != fingerprint:
        return False
    return row["removed_at"] >= updated


def _clear_removed(conn, user_id, kind, job_id):
    conn.execute(
        "DELETE FROM removed WHERE user_id = ? AND kind = ? AND job_id = ?",
        (user_id, kind, job_id),
    )


def _tombstone(conn, user_id, kind, job_id, now_ms, fingerprint=""):
    conn.execute(
        """INSERT INTO removed (user_id, kind, job_id, removed_at, fingerprint)
           VALUES (?,?,?,?,?)
           ON CONFLICT(user_id, kind, job_id) DO UPDATE SET
             removed_at = max(removed.removed_at, excluded.removed_at),
             fingerprint = CASE
               WHEN excluded.fingerprint != '' THEN excluded.fingerprint
               ELSE removed.fingerprint
             END""",
        (user_id, kind, job_id, int(now_ms), fingerprint or ""),
    )


def _report_key(kind, rec):
    """Name key shared by a saved report and the draft of that same sheet."""
    if not isinstance(rec, dict):
        return ""
    if kind == "pump":
        name = str(rec.get("jobName") or "").strip().lower()
        year = str(rec.get("year") or "")
        pump = str(rec.get("pumpId") or "").strip().lower()
        key = "%s|%s|%s" % (name, year, pump)
        return "" if key == "||" else key
    if kind in ("hydro", "tank", "flow"):
        return str(rec.get("site") or rec.get("title") or "").strip().lower()
    if kind == "fan":
        parts = [str(rec.get(field) or "").strip().lower() for field in ("client", "enclosure", "jobNo")]
        key = "|".join(parts)
        return "" if key == "||" else key
    return ""


def _drop_same_draft(conn, user_id, kind, rec, now_ms):
    """Drop the draft when it is the report that was just deleted."""
    wanted = _report_key(kind, rec)
    if not wanted:
        return False
    row = conn.execute(
        "SELECT payload FROM drafts WHERE user_id = ? AND kind = ?",
        (user_id, kind),
    ).fetchone()
    if not row:
        return False
    try:
        draft = json.loads(row["payload"])
    except json.JSONDecodeError:
        return False
    if _report_key(kind, draft) != wanted:
        return False
    conn.execute(
        "DELETE FROM drafts WHERE user_id = ? AND kind = ?",
        (user_id, kind),
    )
    prior = _as_ms(draft.get("updated"))
    stamp = now_ms if prior is None else max(now_ms, prior)
    _tombstone(conn, user_id, kind, "", stamp, _job_fingerprint(draft))
    return True


def remove_job(user_id, kind, job_id="", draft=False):
    """Delete one saved report or draft and stop an older copy coming back."""
    if kind not in KINDS:
        raise ValueError("This file has no report.")
    job_id = "" if draft else str(job_id or "")
    if not draft and not ID_RE.match(job_id):
        raise ValueError("This saved job has no id.")
    init_db()
    now_ms = int(time.time() * 1000)
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        removed_rec = None
        if draft:
            row = conn.execute(
                "SELECT payload FROM drafts WHERE user_id = ? AND kind = ?",
                (user_id, kind),
            ).fetchone()
            cur = conn.execute(
                "DELETE FROM drafts WHERE user_id = ? AND kind = ?",
                (user_id, kind),
            )
        else:
            row = conn.execute(
                "SELECT payload FROM jobs WHERE user_id = ? AND kind = ? AND job_id = ?",
                (user_id, kind, job_id),
            ).fetchone()
            cur = conn.execute(
                "DELETE FROM jobs WHERE user_id = ? AND kind = ? AND job_id = ?",
                (user_id, kind, job_id),
            )
        if row:
            try:
                removed_rec = json.loads(row["payload"])
            except json.JSONDecodeError:
                removed_rec = None
        if cur.rowcount < 1:
            raise ValueError("That report is already gone.")
        prior = _as_ms(removed_rec.get("updated")) if isinstance(removed_rec, dict) else None
        stamp = now_ms if prior is None else max(now_ms, prior)
        finger = _job_fingerprint(removed_rec) if isinstance(removed_rec, dict) else ""
        _tombstone(conn, user_id, kind, job_id, stamp, finger)
        if not draft and isinstance(removed_rec, dict):
            _drop_same_draft(conn, user_id, kind, removed_rec, now_ms)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_DUP_SKIP = ("id", "updated", "sharedBy")


def _job_fingerprint(rec):
    """Identity of a report, ignoring its id and the share label."""
    body = {key: rec[key] for key in rec if key not in _DUP_SKIP}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _collapse_duplicate_jobs(conn, user_id, kind, now_ms):
    """Keep one row when the same report was stored under two ids.

    A shared copy is kept ahead of a later autosave of that same report.
    The extra id is tombstoned so the phone does not put it back.
    """
    rows = conn.execute(
        "SELECT job_id, payload, updated_at FROM jobs WHERE user_id = ? AND kind = ?",
        (user_id, kind),
    ).fetchall()
    groups = {}
    for row in rows:
        try:
            rec = json.loads(row["payload"])
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        groups.setdefault(_job_fingerprint(rec), []).append((row, rec))
    removed = 0
    for items in groups.values():
        if len(items) < 2:
            continue

        def rank(item):
            row, rec = item
            shared = 0 if rec.get("sharedBy") else 1
            return (shared, row["updated_at"], str(row["job_id"]))

        items.sort(key=rank)
        for row, rec in items[1:]:
            conn.execute(
                "DELETE FROM jobs WHERE user_id = ? AND kind = ? AND job_id = ?",
                (user_id, kind, row["job_id"]),
            )
            prior = int(row["updated_at"] or 0)
            _tombstone(
                conn,
                user_id,
                kind,
                row["job_id"],
                now_ms if prior < now_ms else prior,
                _job_fingerprint(rec),
            )
            removed += 1
    return removed


def _share_id(owner_id, kind, job_id):
    """Stable id so sharing the same report again updates that copy."""
    digest = hashlib.sha256(("%s|%s|%s" % (owner_id, kind, job_id)).encode("utf-8")).hexdigest()[:20]
    return "s" + digest


def share_job(owner_id, kind, job_id, to_name):
    """Copy one saved job onto another account. The owner's copy is left as it is."""
    if kind not in KINDS:
        raise ValueError("This report could not be shared.")
    job_id = str(job_id or "")
    if not ID_RE.match(job_id):
        raise ValueError("This report could not be shared.")
    try:
        owner_id = int(owner_id)
    except (TypeError, ValueError):
        raise ValueError("This report could not be shared.") from None
    to_name = _clean_username(to_name)
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        owner = conn.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (owner_id,),
        ).fetchone()
        if not owner:
            raise ValueError("This report could not be shared.")
        if owner["username"].lower() == to_name.lower():
            raise ValueError("Share it with someone else.")
        target = conn.execute(
            "SELECT id, username FROM users WHERE username = ? COLLATE NOCASE",
            (to_name,),
        ).fetchone()
        if not target:
            raise ValueError("No such account.")
        row = conn.execute(
            "SELECT payload FROM jobs WHERE user_id = ? AND kind = ? AND job_id = ?",
            (owner_id, kind, job_id),
        ).fetchone()
        if not row:
            raise ValueError("Save the report before sharing it.")
        try:
            rec = json.loads(row["payload"])
        except json.JSONDecodeError:
            rec = None
        if not isinstance(rec, dict):
            raise ValueError("This report could not be shared.")
        shared_id = _share_id(owner_id, kind, job_id)
        updated = int(time.time() * 1000)
        stored = dict(rec)
        stored["id"] = shared_id
        stored["updated"] = updated
        stored["sharedBy"] = owner["username"]
        blob = json.dumps(stored, separators=(",", ":"), ensure_ascii=False)
        if len(blob) > 200_000:
            raise ValueError("That report is too large to share.")
        existing = conn.execute(
            "SELECT 1 FROM jobs WHERE user_id = ? AND kind = ? AND job_id = ?",
            (target["id"], kind, shared_id),
        ).fetchone()
        if not existing:
            count = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE user_id = ? AND kind = ?",
                (target["id"], kind),
            ).fetchone()[0]
            if count >= 80:
                raise ValueError("That account already has 80 saved jobs.")
        _clear_removed(conn, target["id"], kind, shared_id)
        conn.execute(
            """INSERT INTO jobs (user_id, kind, job_id, payload, updated_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(user_id, kind, job_id) DO UPDATE SET
                 payload = excluded.payload,
                 updated_at = excluded.updated_at""",
            (target["id"], kind, shared_id, blob, updated),
        )
        _collapse_duplicate_jobs(conn, target["id"], kind, updated)
        conn.commit()
        return {"username": target["username"], "id": shared_id}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _sync(user_id, data):
    jobs_in = data.get("jobs") if isinstance(data.get("jobs"), dict) else {}
    known_in = data.get("known") if isinstance(data.get("known"), dict) else {}
    drafts_in = data.get("drafts") if isinstance(data.get("drafts"), dict) else {}
    conn = connect()
    now_ms = int(time.time() * 1000)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for kind in KINDS:
            incoming = jobs_in.get(kind)
            if not isinstance(incoming, list):
                incoming = []
            seen = set()
            blocked = []
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
                if _removed_blocks(conn, user_id, kind, job_id, updated, _job_fingerprint(stored)):
                    blocked.append(stored)
                    continue
                blob = json.dumps(stored, separators=(",", ":"), ensure_ascii=False)
                if len(blob) > 200_000:
                    continue
                _clear_removed(conn, user_id, kind, job_id)
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
            deleted = []
            if isinstance(known, list):
                for item in known[:200]:
                    job_id = str(item or "")
                    if ID_RE.match(job_id) and job_id not in seen:
                        row = conn.execute(
                            "SELECT payload FROM jobs WHERE user_id = ? AND kind = ? AND job_id = ?",
                            (user_id, kind, job_id),
                        ).fetchone()
                        conn.execute(
                            "DELETE FROM jobs WHERE user_id = ? AND kind = ? AND job_id = ?",
                            (user_id, kind, job_id),
                        )
                        parsed = None
                        if row:
                            try:
                                parsed = json.loads(row["payload"])
                            except json.JSONDecodeError:
                                parsed = None
                            if isinstance(parsed, dict):
                                deleted.append(parsed)
                        prior = _as_ms(parsed.get("updated")) if isinstance(parsed, dict) else None
                        stamp = now_ms if prior is None else max(now_ms, prior)
                        finger = _job_fingerprint(parsed) if isinstance(parsed, dict) else ""
                        _tombstone(conn, user_id, kind, job_id, stamp, finger)
            for rec in blocked:
                job_id = str(rec.get("id") or "")
                updated = _as_ms(rec.get("updated")) or now_ms
                _tombstone(
                    conn,
                    user_id,
                    kind,
                    job_id,
                    max(now_ms, updated),
                    _job_fingerprint(rec),
                )
            for rec in blocked + deleted:
                _drop_same_draft(conn, user_id, kind, rec, now_ms)
            _collapse_duplicate_jobs(conn, user_id, kind, now_ms)
            draft = drafts_in.get(kind)
            if isinstance(draft, dict):
                updated = _as_ms(draft.get("updated"))
                if updated is None:
                    continue
                if _removed_blocks(conn, user_id, kind, "", updated, _job_fingerprint(draft)):
                    continue
                blob = json.dumps(draft, separators=(",", ":"), ensure_ascii=False)
                if len(blob) > 200_000:
                    continue
                _clear_removed(conn, user_id, kind, "")
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
            minutes = max(1, (_reg_wait(ip) + 59) // 60)
            return _err(
                429,
                "Too many new accounts. Try again in %d minute%s."
                % (minutes, "" if minutes == 1 else "s"),
            )
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
        _note_reg(ip)
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
            import calibration
            calibration.forget_user(target)
            conn.execute("DELETE FROM users WHERE id = ?", (target,))
            conn.commit()
        finally:
            conn.close()
        return _ok({"ok": True})
    if path == "/api/people" and method == "GET":
        if not user:
            return _err(401, "Sign in.")
        conn = connect()
        try:
            rows = conn.execute(
                "SELECT username FROM users WHERE id != ? ORDER BY username COLLATE NOCASE",
                (user["id"],),
            ).fetchall()
        finally:
            conn.close()
        return _ok({"people": [row["username"] for row in rows]})
    if path == "/api/share" and method == "POST":
        if not user:
            return _err(401, "Sign in.")
        try:
            shared = share_job(user["id"], data.get("kind"), data.get("id"), data.get("to"))
        except ValueError as exc:
            return _err(400, str(exc))
        except sqlite3.Error:
            return _err(500, "The server could not share that report.")
        return _ok({"ok": True, "username": shared["username"]})
    if path == "/api/sync" and method == "POST":
        if not user:
            return _err(401, "Sign in.")
        try:
            state = _sync(user["id"], data if isinstance(data, dict) else {})
        except sqlite3.Error:
            return _err(500, "The server could not save that job.")
        return _ok(state)
    return _err(404, "Not found.")
