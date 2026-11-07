"""Per-account calibration records for FitterCalcs.

Equipment, certificates, and certificate files belong to the signed-in
account, the same way pump, hydro, tank, and fan jobs do. The phone keeps
its own copy and sends it here. The newer timestamp wins. A delete stays
deleted until a later edit of that same record arrives.
"""

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

import accounts

MAX_FILE = 20 * 1024 * 1024
MAX_EQUIPMENT = 2000
MAX_CERTIFICATES = 8000
MAX_REMOVED = 4000
UID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
FILE_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
RESULTS = ("Pass", "Pass with findings", "Fail", "Not stated")


def _root():
    return accounts.DB.parent / "calibration"


def _user_dir(user_id):
    return _root() / str(int(user_id))


def _data_path(user_id, uid):
    return _user_dir(user_id) / uid


def _sha_path(user_id, uid):
    return _user_dir(user_id) / ("%s.sha" % uid)


def ensure_schema():
    accounts.init_db()
    conn = accounts.connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cal_equipment (
                user_id INTEGER NOT NULL,
                uid TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, uid),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS cal_certificates (
                user_id INTEGER NOT NULL,
                uid TEXT NOT NULL,
                equipment_uid TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, uid),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS cal_removed (
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                uid TEXT NOT NULL,
                removed_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, kind, uid),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()
    finally:
        conn.close()
    try:
        os.chmod(_root(), 0o700)
    except OSError:
        pass


def forget_user(user_id):
    ensure_schema()
    conn = accounts.connect()
    try:
        conn.execute("DELETE FROM cal_certificates WHERE user_id = ?", (int(user_id),))
        conn.execute("DELETE FROM cal_equipment WHERE user_id = ?", (int(user_id),))
        conn.execute("DELETE FROM cal_removed WHERE user_id = ?", (int(user_id),))
        conn.commit()
    finally:
        conn.close()
    folder = _user_dir(user_id)
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)


def handle(method, path, data, token, ip, origin="", host=""):
    del ip
    ensure_schema()
    if method in ("POST", "DELETE") and not accounts._origin_ok(origin, host):
        return accounts._err(403, "Blocked.")
    user = accounts._user_for_token(token)
    if path == "/api/calibration/sync" and method == "POST":
        if not user:
            return accounts._err(401, "Sign in.")
        try:
            state = _sync(user["id"], data if isinstance(data, dict) else {})
        except ValueError as exc:
            return accounts._err(400, str(exc))
        except Exception:
            return accounts._err(500, "The server could not save those records.")
        state["username"] = user["username"]
        return accounts._ok(state)
    return accounts._err(404, "Not found.")


def read_file(token, path):
    ensure_schema()
    user = accounts._user_for_token(token)
    if not user:
        return _file_error(401, "Sign in.")
    uid = _file_uid(path)
    if not uid:
        return _file_error(404, "Not found.")
    conn = accounts.connect()
    try:
        row = conn.execute(
            """SELECT payload FROM cal_certificates
               WHERE user_id = ? AND uid = ?""",
            (user["id"], uid),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return _file_error(404, "No such certificate.")
    data_path = _data_path(user["id"], uid)
    if not data_path.is_file() or _stored_sha(user["id"], uid) == "":
        return _file_error(404, "That certificate has no file.")
    try:
        payload = json.loads(row["payload"])
    except json.JSONDecodeError:
        payload = {}
    mime = payload.get("attachmentMime") or "application/octet-stream"
    if mime not in FILE_TYPES:
        mime = "application/octet-stream"
    name = _safe_name(payload.get("attachmentName") or "", mime)
    return FileResult(200, data=data_path.read_bytes(), content_type=mime, filename=name)


def write_file(token, path, raw, content_type, filename, claimed_sha, origin="", host=""):
    ensure_schema()
    if not accounts._origin_ok(origin, host):
        return _file_error(403, "Blocked.")
    user = accounts._user_for_token(token)
    if not user:
        return _file_error(401, "Sign in.")
    uid = _file_uid(path)
    if not uid:
        return _file_error(404, "Not found.")
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        return _file_error(400, "The file was empty.")
    if len(raw) > MAX_FILE:
        return _file_error(413, "That file is too large.")
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime not in FILE_TYPES:
        return _file_error(400, "Use a PDF or a photo.")
    digest = hashlib.sha256(raw).hexdigest()
    claimed = (claimed_sha or "").strip().lower()
    if claimed and claimed != digest:
        return _file_error(400, "The file did not match.")
    conn = accounts.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT payload, updated_at FROM cal_certificates
               WHERE user_id = ? AND uid = ?""",
            (user["id"], uid),
        ).fetchone()
        if not row:
            conn.rollback()
            return _file_error(404, "No such certificate.")
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        existing_sha = str(payload.get("attachmentSha") or "").lower()
        if existing_sha and existing_sha != digest:
            conn.rollback()
            return _file_error(400, "The file did not match.")
        folder = _user_dir(user["id"])
        folder.mkdir(parents=True, mode=0o700, exist_ok=True)
        target = _data_path(user["id"], uid)
        temporary = folder / ("%s.part" % uid)
        temporary.write_bytes(raw)
        os.chmod(temporary, 0o600)
        temporary.replace(target)
        sha_file = _sha_path(user["id"], uid)
        sha_file.write_text(digest, encoding="ascii")
        os.chmod(sha_file, 0o600)
        payload["attachmentSha"] = digest
        payload["attachmentMime"] = mime
        safe = _safe_name(filename, mime)
        if safe:
            payload["attachmentName"] = safe
        conn.execute(
            """UPDATE cal_certificates SET payload = ? WHERE user_id = ? AND uid = ?""",
            (json.dumps(payload, separators=(",", ":"), ensure_ascii=False), user["id"], uid),
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return _file_error(500, "The server could not save that file.")
    finally:
        conn.close()
    return FileResult(200, body={"ok": True, "sha": digest})


class FileResult:
    def __init__(self, status, body=None, data=None, content_type="", filename=""):
        self.status = status
        self.body = body if body is not None else {}
        self.data = data
        self.content_type = content_type
        self.filename = filename


def _file_error(status, message):
    return FileResult(status, body={"error": message})


def _file_uid(path):
    prefix = "/api/calibration/file/"
    if not path.startswith(prefix):
        return ""
    uid = path[len(prefix):]
    if not UID_RE.match(uid):
        return ""
    return uid


def _stored_sha(user_id, uid):
    path = _sha_path(user_id, uid)
    data_path = _data_path(user_id, uid)
    if not path.is_file() or not data_path.is_file():
        return ""
    try:
        return path.read_text(encoding="ascii").strip().lower()
    except OSError:
        return ""


def _text(value, limit):
    if not isinstance(value, str):
        if value is None:
            return ""
        value = str(value)
    cleaned = "".join(ch for ch in value if ch >= " " or ch in "\n\t")
    return cleaned.strip()[:limit]


def _safe_name(value, mime):
    name = _text(value, 80)
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._ -]", "", name).strip(" .")
    suffix = FILE_TYPES.get(mime, "")
    if not name:
        return "certificate%s" % suffix
    if suffix and not name.lower().endswith(suffix):
        stem = name.rsplit(".", 1)[0] if "." in name else name
        name = (stem[:70] or "certificate") + suffix
    return name[:80]


def _sync(user_id, data):
    ensure_schema()
    equipment = data.get("equipment") if isinstance(data.get("equipment"), list) else []
    certificates = data.get("certificates") if isinstance(data.get("certificates"), list) else []
    removed = data.get("removed") if isinstance(data.get("removed"), list) else []
    if (
        len(equipment) > MAX_EQUIPMENT
        or len(certificates) > MAX_CERTIFICATES
        or len(removed) > MAX_REMOVED
    ):
        raise ValueError("That upload has too many records.")
    conn = accounts.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        for item in removed:
            _apply_removal(conn, user_id, item)
        for item in equipment:
            _apply_equipment(conn, user_id, item)
        known = {
            row["uid"]
            for row in conn.execute(
                "SELECT uid FROM cal_equipment WHERE user_id = ?",
                (user_id,),
            )
        }
        for item in certificates:
            _apply_certificate(conn, user_id, item, known)
        state = _dump(conn, user_id)
        conn.commit()
        return state
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _apply_removal(conn, user_id, item):
    if not isinstance(item, dict):
        return
    kind = item.get("kind")
    uid = item.get("uid")
    removed_at = accounts._as_ms(item.get("removedAt"))
    if kind not in ("equipment", "certificate") or not isinstance(uid, str) or not UID_RE.match(uid):
        return
    if removed_at is None:
        return
    if kind == "equipment":
        row = conn.execute(
            "SELECT updated_at FROM cal_equipment WHERE user_id = ? AND uid = ?",
            (user_id, uid),
        ).fetchone()
        if row and row["updated_at"] > removed_at:
            return
        _remove_equipment(conn, user_id, uid, removed_at)
        return
    row = conn.execute(
        "SELECT updated_at FROM cal_certificates WHERE user_id = ? AND uid = ?",
        (user_id, uid),
    ).fetchone()
    if row and row["updated_at"] > removed_at:
        return
    _remove_certificate(conn, user_id, uid, removed_at)


def _remove_equipment(conn, user_id, uid, removed_at):
    certs = conn.execute(
        "SELECT uid, updated_at FROM cal_certificates WHERE user_id = ? AND equipment_uid = ?",
        (user_id, uid),
    ).fetchall()
    for cert in certs:
        _remove_certificate(conn, user_id, cert["uid"], max(removed_at, cert["updated_at"]))
    conn.execute(
        "DELETE FROM cal_equipment WHERE user_id = ? AND uid = ?",
        (user_id, uid),
    )
    _tombstone(conn, user_id, "equipment", uid, removed_at)


def _remove_certificate(conn, user_id, uid, removed_at):
    conn.execute(
        "DELETE FROM cal_certificates WHERE user_id = ? AND uid = ?",
        (user_id, uid),
    )
    _tombstone(conn, user_id, "certificate", uid, removed_at)
    _delete_files(user_id, uid)


def _tombstone(conn, user_id, kind, uid, removed_at):
    conn.execute(
        """INSERT INTO cal_removed (user_id, kind, uid, removed_at)
           VALUES (?,?,?,?)
           ON CONFLICT(user_id, kind, uid) DO UPDATE SET
             removed_at = max(cal_removed.removed_at, excluded.removed_at)""",
        (user_id, kind, uid, removed_at),
    )


def _clear_tombstone(conn, user_id, kind, uid):
    conn.execute(
        "DELETE FROM cal_removed WHERE user_id = ? AND kind = ? AND uid = ?",
        (user_id, kind, uid),
    )


def _blocked(conn, user_id, kind, uid, updated):
    row = conn.execute(
        "SELECT removed_at FROM cal_removed WHERE user_id = ? AND kind = ? AND uid = ?",
        (user_id, kind, uid),
    ).fetchone()
    return row is not None and row["removed_at"] >= updated


def _apply_equipment(conn, user_id, item):
    if not isinstance(item, dict):
        return
    uid = item.get("uid")
    updated = accounts._as_ms(item.get("updated"))
    name = _text(item.get("name"), 120)
    if not isinstance(uid, str) or not UID_RE.match(uid) or updated is None or not name:
        return
    if _blocked(conn, user_id, "equipment", uid, updated):
        return
    count = conn.execute(
        "SELECT COUNT(*) FROM cal_equipment WHERE user_id = ?",
        (user_id,),
    ).fetchone()[0]
    existing = conn.execute(
        "SELECT updated_at FROM cal_equipment WHERE user_id = ? AND uid = ?",
        (user_id, uid),
    ).fetchone()
    if existing and existing["updated_at"] > updated:
        return
    if not existing and count >= MAX_EQUIPMENT:
        return
    interval = item.get("calibrationIntervalMonths")
    if isinstance(interval, bool) or not isinstance(interval, (int, float)):
        interval = 12
    interval = int(interval)
    if interval < 1:
        interval = 1
    if interval > 120:
        interval = 120
    payload = {
        "uid": uid,
        "name": name,
        "category": _text(item.get("category"), 80),
        "manufacturer": _text(item.get("manufacturer"), 80),
        "model": _text(item.get("model"), 80),
        "serialNumber": _text(item.get("serialNumber"), 80),
        "location": _text(item.get("location"), 80),
        "standardReference": _text(item.get("standardReference"), 80),
        "calibrationIntervalMonths": interval,
        "notes": _text(item.get("notes"), 2000),
    }
    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    conn.execute(
        """INSERT INTO cal_equipment (user_id, uid, payload, updated_at)
           VALUES (?,?,?,?)
           ON CONFLICT(user_id, uid) DO UPDATE SET
             payload = excluded.payload,
             updated_at = excluded.updated_at""",
        (user_id, uid, blob, updated),
    )
    _clear_tombstone(conn, user_id, "equipment", uid)


def _apply_certificate(conn, user_id, item, equipment_uids):
    if not isinstance(item, dict):
        return
    uid = item.get("uid")
    equipment_uid = item.get("equipmentUid")
    updated = accounts._as_ms(item.get("updated"))
    calibrated = accounts._as_ms(item.get("calibrationDate"))
    due = accounts._as_ms(item.get("nextDueDate"))
    if (
        not isinstance(uid, str)
        or not UID_RE.match(uid)
        or not isinstance(equipment_uid, str)
        or equipment_uid not in equipment_uids
        or updated is None
        or calibrated is None
        or due is None
    ):
        return
    if _blocked(conn, user_id, "certificate", uid, updated):
        return
    count = conn.execute(
        "SELECT COUNT(*) FROM cal_certificates WHERE user_id = ?",
        (user_id,),
    ).fetchone()[0]
    existing = conn.execute(
        """SELECT payload, updated_at FROM cal_certificates
           WHERE user_id = ? AND uid = ?""",
        (user_id, uid),
    ).fetchone()
    if existing and existing["updated_at"] > updated:
        return
    if not existing and count >= MAX_CERTIFICATES:
        return
    result = _text(item.get("result"), 40) or "Not stated"
    if result not in RESULTS:
        result = "Not stated"
    created = accounts._as_ms(item.get("createdAt")) or calibrated
    sha = _text(item.get("attachmentSha"), 64).lower()
    if sha and not re.fullmatch(r"[0-9a-f]{64}", sha):
        sha = ""
    mime = _text(item.get("attachmentMime"), 40).lower()
    if mime not in FILE_TYPES:
        mime = ""
    previous_sha = ""
    if existing:
        try:
            previous = json.loads(existing["payload"])
            previous_sha = str(previous.get("attachmentSha") or "").lower()
        except json.JSONDecodeError:
            previous_sha = ""
    payload = {
        "uid": uid,
        "equipmentUid": equipment_uid,
        "certificateNumber": _text(item.get("certificateNumber"), 80),
        "calibrationDate": calibrated,
        "nextDueDate": due,
        "labName": _text(item.get("labName"), 80),
        "accreditation": _text(item.get("accreditation"), 40),
        "result": result,
        "standardReference": _text(item.get("standardReference"), 80),
        "notes": _text(item.get("notes"), 2000),
        "createdAt": created,
        "attachmentName": _safe_name(item.get("attachmentName") or "", mime) if mime or sha else "",
        "attachmentMime": mime,
        "attachmentSha": sha,
    }
    if sha != previous_sha:
        _delete_files(user_id, uid)
    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    conn.execute(
        """INSERT INTO cal_certificates
           (user_id, uid, equipment_uid, payload, updated_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(user_id, uid) DO UPDATE SET
             equipment_uid = excluded.equipment_uid,
             payload = excluded.payload,
             updated_at = excluded.updated_at""",
        (user_id, uid, equipment_uid, blob, updated),
    )
    _clear_tombstone(conn, user_id, "certificate", uid)


def _delete_files(user_id, uid):
    for path in (_data_path(user_id, uid), _sha_path(user_id, uid)):
        try:
            path.unlink()
        except OSError:
            pass


def _dump(conn, user_id):
    equipment = []
    for row in conn.execute(
        "SELECT uid, payload, updated_at FROM cal_equipment WHERE user_id = ? ORDER BY uid",
        (user_id,),
    ):
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        payload["uid"] = row["uid"]
        payload["updated"] = row["updated_at"]
        equipment.append(payload)
    certificates = []
    for row in conn.execute(
        """SELECT uid, equipment_uid, payload, updated_at
           FROM cal_certificates WHERE user_id = ? ORDER BY uid""",
        (user_id,),
    ):
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        payload["uid"] = row["uid"]
        payload["equipmentUid"] = row["equipment_uid"]
        payload["updated"] = row["updated_at"]
        sha = str(payload.get("attachmentSha") or "").lower()
        payload["hasFile"] = bool(sha) and _stored_sha(user_id, row["uid"]) == sha
        certificates.append(payload)
    removed = []
    for row in conn.execute(
        """SELECT kind, uid, removed_at FROM cal_removed
           WHERE user_id = ? ORDER BY removed_at""",
        (user_id,),
    ):
        removed.append(
            {"kind": row["kind"], "uid": row["uid"], "removedAt": row["removed_at"]}
        )
    return {"equipment": equipment, "certificates": certificates, "removed": removed}
