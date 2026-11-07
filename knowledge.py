#!/usr/bin/env python3
"""Local document library for the FitterCalcs Ask assistant.

The library is a folder of documents on this PC.  This module extracts text,
keeps page and clause metadata, splits the text into chunks, and stores the
chunks in a local SQLite FTS5 index.  Nothing here talks to the internet.

Commands:
    python3 knowledge.py sync [--no-ocr] [--ocr-all]
    python3 knowledge.py list
    python3 knowledge.py stats
    python3 knowledge.py search "hydrant storage"
    python3 knowledge.py ask "what does AS 2419.1 say about storage?"
"""

from __future__ import annotations

import argparse
import csv
import email
import fcntl
import hashlib
import html.parser
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree

LIBRARY = Path(
    os.environ.get("FITTERCALCS_DOCS")
    or (Path.home() / "Documents" / "FitterDocs")
)
DATA = Path(
    os.environ.get("FITTERCALCS_ASSISTANT_DATA")
    or (Path.home() / ".local/share/fittercalcs/assistant")
)
DB = DATA / "knowledge.db"
LOCK = DATA / "index.lock"

SUPPORTED = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".txt", ".md", ".markdown", ".csv", ".html", ".htm", ".eml",
    ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp",
}

CHUNK_CHARS = 1400
CHUNK_OVERLAP = 220
MAX_OCR_PAGES = 60
MAX_TEXT_CHARS = 12_000_000

STOPWORDS = {
    "a", "an", "the", "of", "to", "in", "on", "at", "by", "for", "from",
    "and", "or", "but", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "what", "which", "who", "whom", "whose", "when",
    "where", "why", "how", "that", "this", "these", "those", "it", "its",
    "i", "me", "my", "we", "our", "you", "your", "can", "could", "should",
    "would", "will", "shall", "may", "might", "must", "please", "tell",
    "give", "show", "about", "with", "without", "into", "over", "under",
    "between", "than", "then", "there", "their", "they", "them", "also",
    "any", "all", "some", "such", "if", "as", "per", "not", "no", "yes",
}


class BusyError(RuntimeError):
    """Another indexing job is already running."""


class ExtractError(RuntimeError):
    """A document could not be read."""


def _now() -> int:
    return int(time.time())


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(DATA, 0o700)
    except OSError:
        pass
    conn = sqlite3.connect(str(DB), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS docs (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                code TEXT,
                edition TEXT,
                pages INTEGER NOT NULL DEFAULT 0,
                size INTEGER NOT NULL DEFAULT 0,
                mtime REAL NOT NULL DEFAULT 0,
                sha256 TEXT NOT NULL,
                added_at INTEGER NOT NULL,
                indexed_at INTEGER NOT NULL,
                text_chars INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'ok',
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL REFERENCES docs(id) ON DELETE CASCADE,
                page INTEGER,
                printed_page TEXT,
                section TEXT,
                text TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS chunks_doc_page
                ON chunks(doc_id, page);
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                content,
                title,
                filename,
                section,
                tokenize='unicode61 remove_diacritics 2'
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

_WATERMARK = re.compile(
    r"^\s*Accessed by .*?\(Document currency not guaranteed when printed\)\s*$",
    re.I,
)
_COPYRIGHT = re.compile(r"^\s*(?:©|\(c\)|Copyright)\s*Standards Australia.*$", re.I)
_WEB = re.compile(r"^\s*(?:www\.)?standards\.org\.au.*$", re.I)
_HEADER = re.compile(
    r"^\s*AS(?:/NZS)?\s+[\dA-Z.]+(?:\s*[—–-]\s*\d{4})?\s+\d{1,4}\s+",
    re.I,
)
_HEADER_ONLY = re.compile(
    r"^\s*AS(?:/NZS)?\s+[\dA-Z.]+(?:\s*[—–-]\s*\d{4})?\s+\d{1,4}\s*$",
    re.I,
)
_APPROVAL = re.compile(
    r"^\s*(?:This is a free \d+ page sample|Licensed to .*|COPYRIGHT|NOT FOR RESALE)\s*$",
    re.I,
)
_SAI_PERMISSION = re.compile(
    r"^\s*Get permission to copy from or network this publication.*$", re.I
)
_SAI_URL = re.compile(r"^\s*.*www\.saiglobal\.com/licensing.*$", re.I)
_SA_STANDALONE = re.compile(r"^\s*Standards Australia\s*$", re.I)
_PAGE_HEADER = re.compile(
    r"^\s*AS(?:/NZS)?\s+([\dA-Z.]+)(?:\s*[—–-]\s*(\d{4}))?\s+(\d{1,4})\s*$",
    re.I,
)
_PAGE_OF = re.compile(r"^\s*Page\s+(\d{1,4})\s+of\s+\d{1,4}\s*$", re.I)
_STANDALONE_HEADER = re.compile(
    r"^\s*AS(?:/NZS)?\s+[\dA-Z.]+(?:\s*[—–-]\s*\d{4})?\s*$",
    re.I,
)


def _norm_space(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\u00ad", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def printed_page_of(raw: str) -> str | None:
    """Return the page number printed on the page, if it can be found."""
    lines = [line.strip() for line in _norm_space(raw).splitlines() if line.strip()]

    def check(block: list[str]) -> str | None:
        for index, line in enumerate(block):
            match = _PAGE_HEADER.match(line)
            if match:
                return match.group(3)
            match = _PAGE_OF.match(line)
            if match:
                return match.group(1)
            # Some standards put the page number first, then the code.
            if re.fullmatch(r"\d{1,4}", line) and index + 1 < len(block):
                if _STANDALONE_HEADER.match(block[index + 1].strip()):
                    return line
            # Some standards put the code, page number and heading on
            # separate lines:  AS 2444—2001 / 2 / PREFACE
            if _STANDALONE_HEADER.match(line) and index + 1 < len(block):
                following = block[index + 1].strip()
                if re.fullmatch(r"\d{1,4}", following):
                    return following
        return None

    return check(lines[:8]) or check(list(reversed(lines[-8:])))


def clean_page(raw: str) -> str:
    """Drop headers, footers, watermarks and stray page numbers."""
    lines = []
    for line in _norm_space(raw).splitlines():
        line = re.sub(r"[ \t]{2,}", " ", line).strip()
        if not line:
            lines.append("")
            continue
        if _WATERMARK.match(line):
            continue
        if _COPYRIGHT.match(line) or _WEB.match(line) or _APPROVAL.match(line):
            continue
        if _SAI_PERMISSION.match(line) or _SAI_URL.search(line) or _SA_STANDALONE.match(line):
            continue
        if _HEADER_ONLY.match(line):
            continue
        header = _HEADER.match(line)
        if header:
            line = line[header.end():].strip()
            if not line:
                continue
        if _PAGE_OF.match(line):
            continue
        if not re.search(r"[A-Za-z0-9]", line):
            continue
        lines.append(line)
    # A bare number at the very top or bottom is a page number, not content.
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and re.fullmatch(r"\d{1,4}", lines[0].strip()):
        lines.pop(0)
    if lines and re.fullmatch(r"\d{1,4}", lines[-1].strip()):
        lines.pop()
    # A standard code on its own line, followed by the page number, is a
    # running header.  Some PDFs put the code, page number and heading on
    # separate lines instead of one line.
    if lines and _STANDALONE_HEADER.match(lines[0].strip()):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and re.fullmatch(r"\d{1,4}", lines[0].strip()):
            lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _run(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def _ocr_page(path: Path, page: int) -> str:
    try:
        with tempfile.TemporaryDirectory(prefix="fc-ocr-") as tmp:
            prefix = Path(tmp) / "page"
            result = _run(
                [
                    "pdftoppm", "-f", str(page), "-l", str(page),
                    "-r", "220", "-gray", "-singlefile", "-png",
                    str(path), str(prefix),
                ],
                timeout=120,
            )
            if result.returncode != 0:
                return ""
            image = Path(str(prefix) + ".png")
            if not image.is_file():
                return ""
            result = _run(
                ["tesseract", str(image), "stdout", "-l", "eng", "--psm", "3"],
                timeout=180,
            )
            if result.returncode != 0:
                return ""
            return result.stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return ""


def extract_pdf(path: Path, ocr: bool = True, ocr_all: bool = False) -> list[dict]:
    # Default mode keeps the reading order.  -layout interleaves the two
    # columns used by most Standards Australia documents and creates huge
    # whitespace-only fragments.
    result = _run(
        ["pdftotext", "-enc", "UTF-8", str(path), "-"],
        timeout=600,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise ExtractError(message or "pdftotext could not read this PDF.")
    raw = result.stdout.decode("utf-8", "replace")
    pages: list[dict] = []
    ocr_count = 0
    for index, page_raw in enumerate(raw.split("\f"), start=1):
        if not page_raw.strip():
            continue
        printed = printed_page_of(page_raw)
        text = clean_page(page_raw)
        if ocr and (ocr_all or len(text.strip()) < 25):
            if ocr_all or ocr_count < MAX_OCR_PAGES:
                ocr_text = clean_page(_ocr_page(path, index))
                if len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
                    ocr_count += 1
        if text.strip():
            pages.append({"page": index, "printed_page": printed, "text": text})
        if sum(len(page["text"]) for page in pages) > MAX_TEXT_CHARS:
            raise ExtractError("This document is too large to index.")
    return pages


class _HtmlText(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4",
                     "h5", "h6", "section", "article", "table"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4",
                     "h5", "h6", "section", "article", "table"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_title:
            self.title += data
        else:
            self.parts.append(data)


def extract_html(path: Path) -> tuple[list[dict], str]:
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", "replace")
    parser = _HtmlText()
    parser.feed(text)
    body = clean_page("".join(parser.parts))
    title = parser.title.strip()
    return ([{"page": 1, "printed_page": None, "text": body}] if body else []), title


def extract_docx(path: Path) -> list[dict]:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile, OSError) as exc:
        raise ExtractError("This Word file could not be opened.") from exc
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise ExtractError("This Word file could not be parsed.") from exc
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    parts: list[str] = []

    def paragraph_text(node) -> str:
        bits = []
        for item in node.iter():
            if item.tag == namespace + "t" and item.text:
                bits.append(item.text)
            elif item.tag == namespace + "tab":
                bits.append("\t")
            elif item.tag == namespace + "br":
                bits.append("\n")
        return "".join(bits)

    def walk(node) -> None:
        for child in node:
            if child.tag == namespace + "p":
                text = paragraph_text(child)
                if text.strip():
                    parts.append(text.strip())
            elif child.tag == namespace + "tbl":
                for row in child.iter(namespace + "tr"):
                    cells = []
                    for cell in row.findall(namespace + "tc"):
                        cells.append(paragraph_text(cell).strip())
                    if any(cells):
                        parts.append(" | ".join(cells))
            else:
                walk(child)

    walk(root)
    text = clean_page("\n".join(parts))
    return ([{"page": 1, "printed_page": None, "text": text}] if text else [])


def extract_office_pdf(path: Path) -> list[dict]:
    if not shutil.which("libreoffice"):
        raise ExtractError("LibreOffice is needed to read this file type.")
    with tempfile.TemporaryDirectory(prefix="fc-office-") as tmp:
        tmp_path = Path(tmp)
        profile = tmp_path / "profile"
        result = _run(
            [
                "libreoffice",
                "--headless",
                "--nologo",
                "--nolockcheck",
                f"-env:UserInstallation=file://{profile}",
                "--convert-to", "pdf",
                "--outdir", str(tmp_path),
                str(path),
            ],
            timeout=300,
        )
        converted = tmp_path / (path.stem + ".pdf")
        if result.returncode != 0 or not converted.is_file():
            message = result.stderr.decode("utf-8", "replace").strip()
            raise ExtractError(message or "LibreOffice could not read this file.")
        return extract_pdf(converted, ocr=False)


def extract_text_file(path: Path) -> list[dict]:
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", "replace")
    text = clean_page(text)
    return ([{"page": 1, "printed_page": None, "text": text}] if text else [])


def extract_eml(path: Path) -> list[dict]:
    message = email.message_from_bytes(path.read_bytes())
    bits = []
    for header in ("Subject", "From", "To", "Date"):
        value = message.get(header)
        if value:
            bits.append(f"{header}: {value}")
    body = ""
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                body = payload.decode(part.get_content_charset() or "utf-8", "replace")
                if body.strip():
                    break
    else:
        payload = message.get_payload(decode=True) or b""
        body = payload.decode(message.get_content_charset() or "utf-8", "replace")
    if body:
        bits.append(body)
    text = clean_page("\n".join(bits))
    return ([{"page": 1, "printed_page": None, "text": text}] if text else [])


def extract_image(path: Path) -> list[dict]:
    if not shutil.which("tesseract"):
        raise ExtractError("Tesseract is needed to read images.")
    result = _run(
        ["tesseract", str(path), "stdout", "-l", "eng", "--psm", "3"],
        timeout=300,
    )
    if result.returncode != 0:
        raise ExtractError("Tesseract could not read this image.")
    text = clean_page(result.stdout.decode("utf-8", "replace"))
    return ([{"page": 1, "printed_page": None, "text": text}] if text else [])


_CODE_RE = re.compile(
    r"\b(AS(?:/NZS)?\s*\d{3,4}(?:\.\d+)*)[\s_-]*(\d{4})\b",
    re.I,
)


def document_identity(path: Path) -> tuple[str, str | None, str | None]:
    name = re.sub(r"\s+", " ", path.stem).strip()
    name = re.sub(r"^(AS(?:/NZS)?)\s*(?=\d)", r"\1 ", name, flags=re.I)
    match = _CODE_RE.search(name)
    if not match:
        return name, None, None
    code = re.sub(r"\s+", " ", match.group(1).upper())
    if code.startswith("AS") and not code.startswith("AS "):
        code = "AS " + code[2:].lstrip()
    return name, code, match.group(2)


def extract_document(path: Path, ocr: bool = True, ocr_all: bool = False) -> tuple[list[dict], str, str | None, str | None]:
    suffix = path.suffix.lower()
    title, code, edition = document_identity(path)
    if suffix == ".pdf":
        pages = extract_pdf(path, ocr=ocr, ocr_all=ocr_all)
    elif suffix == ".docx":
        pages = extract_docx(path)
    elif suffix in (".doc", ".xlsx", ".xls", ".pptx", ".ppt"):
        pages = extract_office_pdf(path)
    elif suffix in (".html", ".htm"):
        pages, html_title = extract_html(path)
        if html_title and len(html_title) > 2:
            title = html_title
    elif suffix == ".eml":
        pages = extract_eml(path)
    elif suffix in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"):
        pages = extract_image(path)
    else:
        pages = extract_text_file(path)
    if not pages:
        raise ExtractError("No readable text was found.")
    return pages, title, code, edition


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

_CLAUSE = re.compile(
    r"^\s*([A-Z]?\d+(?:\.\d+){1,5})\s+([A-Z][^\n]{2,150})$"
)
_TABLE = re.compile(
    r"^\s*(TABLE|FIGURE)\s+([A-Z]?\d+(?:\.\d+){0,5})\s*(.*)$",
    re.I,
)
_APPENDIX = re.compile(r"^\s*(APPENDIX)\s+([A-Z])\s*(.*)$", re.I)


def _clause_number_ok(number: str) -> bool:
    """Reject standard references such as 4118.1.1 or 1841.4.

    Real clause numbers start with one to three digits (or a letter and one
    to three digits, e.g. A3.5).  A four-digit first component is almost
    always another Standard's number, not a clause in this document.
    """
    match = re.match(r"([A-Z]?)(\d+)", number)
    return bool(match and len(match.group(2)) <= 3)


def heading_of(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or len(stripped) > 170:
        return None
    match = _CLAUSE.match(stripped)
    if match and _clause_number_ok(match.group(1)):
        return f"Cl {match.group(1)}"
    match = _TABLE.match(stripped)
    if match and _clause_number_ok(match.group(2)):
        kind = "Table" if match.group(1).upper() == "TABLE" else "Figure"
        return f"{kind} {match.group(2)}"
    match = _APPENDIX.match(stripped)
    if match:
        return f"Appendix {match.group(2).upper()}"
    return None


def _split_long(text: str, limit: int) -> list[str]:
    """Split a long paragraph at sentence/line boundaries, without overlap."""
    if len(text) <= limit:
        return [text]
    parts = []
    start = 0
    length = len(text)
    while start < length:
        end = min(length, start + limit)
        if end >= length:
            parts.append(text[start:])
            break
        cut = max(
            text.rfind(". ", start, end),
            text.rfind("\n", start, end),
            text.rfind("; ", start, end),
        )
        if cut > start + limit // 2:
            end = cut + 1
        parts.append(text[start:end])
        if end <= start:
            end = start + 1
        start = end
    return parts


def chunk_text(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text)
    pieces: list[str] = []
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= limit:
            pieces.append(paragraph)
        else:
            pieces.extend(_split_long(paragraph, limit))
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if not current:
            current = piece
        elif len(current) + 2 + len(piece) <= limit:
            current += "\n\n" + piece
        else:
            chunks.append(current)
            tail = current[-CHUNK_OVERLAP:]
            cut = tail.find(" ")
            if cut != -1:
                tail = tail[cut + 1:]
            current = (tail + "\n\n" + piece).strip()
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if len(chunk.strip()) >= 20]


def page_chunks(page: dict, title: str, carry: str | None) -> tuple[list[dict], str | None]:
    # Contents and referenced-document pages are lists of headings and page
    # numbers.  Treat them as ordinary text so they do not become one tiny
    # chunk per line or create false clause numbers.
    head = page["text"][:1200].upper()
    if any(
        marker in head
        for marker in ("CONTENTS", "REFERENCED DOCUMENTS", "REFERENCED STANDARDS")
    ):
        chunks = [
            {
                "page": page["page"],
                "printed_page": page.get("printed_page"),
                "section": None,
                "text": piece,
            }
            for piece in chunk_text(page["text"])
        ]
        return chunks, carry
    section = carry
    buffer: list[str] = []
    chunks: list[dict] = []

    def flush() -> None:
        nonlocal buffer
        body = "\n".join(buffer).strip()
        if not body:
            buffer = []
            return
        for piece in chunk_text(body):
            chunks.append(
                {
                    "page": page["page"],
                    "printed_page": page.get("printed_page"),
                    "section": section,
                    "text": piece,
                }
            )
        buffer = []

    for line in page["text"].splitlines():
        heading = heading_of(line)
        if heading:
            flush()
            section = heading
        buffer.append(line)
    flush()
    return chunks, section


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _delete_doc(conn: sqlite3.Connection, doc_id: str) -> None:
    conn.execute(
        "DELETE FROM chunks_fts WHERE rowid IN "
        "(SELECT id FROM chunks WHERE doc_id = ?)",
        (doc_id,),
    )
    conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM docs WHERE id = ?", (doc_id,))


def _store_error(conn: sqlite3.Connection, path: Path, sha: str, message: str) -> None:
    existing = conn.execute(
        "SELECT id FROM docs WHERE filename = ?", (path.name,)
    ).fetchone()
    if existing:
        _delete_doc(conn, existing["id"])
    doc_id = sha[:16]
    now = _now()
    stat = path.stat()
    conn.execute(
        """INSERT OR REPLACE INTO docs
           (id, filename, title, code, edition, pages, size, mtime, sha256,
            added_at, indexed_at, text_chars, status, error)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            doc_id, path.name, path.stem.strip(), None, None, 0,
            stat.st_size, stat.st_mtime, sha, now, now, 0, "error", message[:500],
        ),
    )
    conn.commit()


def index_document(
    conn: sqlite3.Connection,
    path: Path,
    ocr: bool = True,
    ocr_all: bool = False,
) -> dict:
    path = path.resolve()
    if path.suffix.lower() not in SUPPORTED:
        raise ExtractError("This file type is not supported.")
    sha = file_sha256(path)
    existing = conn.execute(
        "SELECT id, status, indexed_at FROM docs WHERE sha256 = ?", (sha,)
    ).fetchone()
    if existing and existing["status"] == "ok":
        return {
            "filename": path.name,
            "status": "skipped",
            "doc_id": existing["id"],
            "chunks": 0,
        }

    old = conn.execute(
        "SELECT id FROM docs WHERE filename = ? OR id = ?",
        (path.name, sha[:16]),
    ).fetchall()
    for row in old:
        _delete_doc(conn, row["id"])
    conn.commit()

    try:
        pages, title, code, edition = extract_document(
            path, ocr=ocr, ocr_all=ocr_all
        )
    except ExtractError as exc:
        _store_error(conn, path, sha, str(exc))
        raise

    doc_id = sha[:16]
    stat = path.stat()
    now = _now()
    text_chars = sum(len(page["text"]) for page in pages)
    conn.execute(
        """INSERT INTO docs
           (id, filename, title, code, edition, pages, size, mtime, sha256,
            added_at, indexed_at, text_chars, status, error)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            doc_id, path.name, title, code, edition, len(pages),
            stat.st_size, stat.st_mtime, sha, now, now, text_chars, "ok", None,
        ),
    )
    count = 0
    carry = None
    for page in pages:
        pieces, carry = page_chunks(page, title, carry)
        for piece in pieces:
            section = piece["section"]
            printed = piece["printed_page"]
            location = printed or piece["page"]
            context = f"{title} | {section or 'page ' + str(location)} | page {location}"
            cursor = conn.execute(
                """INSERT INTO chunks
                   (doc_id, page, printed_page, section, text)
                   VALUES (?,?,?,?,?)""",
                (doc_id, piece["page"], printed, section, piece["text"]),
            )
            chunk_id = cursor.lastrowid
            conn.execute(
                """INSERT INTO chunks_fts
                   (rowid, content, title, filename, section)
                   VALUES (?,?,?,?,?)""",
                (chunk_id, context + "\n" + piece["text"], title, path.name, section or ""),
            )
            count += 1
    conn.execute(
        """UPDATE docs SET indexed_at = ?, pages = ?, text_chars = ?
           WHERE id = ?""",
        (now, len(pages), text_chars, doc_id),
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('last_sync', ?)",
        (str(now),),
    )
    conn.commit()
    return {
        "filename": path.name,
        "status": "indexed",
        "doc_id": doc_id,
        "pages": len(pages),
        "chunks": count,
        "chars": text_chars,
        "code": code,
        "edition": edition,
    }


def library_files() -> list[Path]:
    if not LIBRARY.is_dir():
        return []
    files = []
    for path in LIBRARY.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED:
            continue
        if ".trash" in path.parts or any(part.startswith(".") for part in path.relative_to(LIBRARY).parts):
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.name.lower())


class IndexLock:
    def __init__(self) -> None:
        self.handle = None

    def __enter__(self):
        DATA.mkdir(parents=True, exist_ok=True)
        self.handle = LOCK.open("a+")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise BusyError("An indexing job is already running.") from exc
        return self

    def __exit__(self, *exc_info):
        if self.handle:
            try:
                fcntl.flock(self.handle, fcntl.LOCK_UN)
            finally:
                self.handle.close()
                self.handle = None


def sync(
    ocr: bool = True,
    ocr_all: bool = False,
    progress=None,
) -> dict:
    init_db()
    with IndexLock():
        files = library_files()
        conn = connect()
        results = []
        errors = []
        try:
            for index, path in enumerate(files, start=1):
                if progress:
                    progress(index, len(files), path.name)
                try:
                    result = index_document(conn, path, ocr=ocr, ocr_all=ocr_all)
                    results.append(result)
                except (ExtractError, OSError, subprocess.SubprocessError) as exc:
                    errors.append({"filename": path.name, "error": str(exc)})
            known = {row["filename"] for row in conn.execute("SELECT filename FROM docs")}
            present = {path.name for path in files}
            removed = 0
            for filename in sorted(known - present):
                row = conn.execute(
                    "SELECT id FROM docs WHERE filename = ?", (filename,)
                ).fetchone()
                if row:
                    _delete_doc(conn, row["id"])
                    removed += 1
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('last_sync', ?)",
                (str(_now()),),
            )
            conn.commit()
        finally:
            conn.close()
    return {
        "files": len(files),
        "indexed": sum(1 for item in results if item["status"] == "indexed"),
        "skipped": sum(1 for item in results if item["status"] == "skipped"),
        "removed": removed,
        "errors": errors,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+-]*")
_QUOTED = re.compile(r'"([^"]{2,120})"')
_CLAUSE_REF = re.compile(
    r"(?i)\b(?:cl(?:ause)?|table|section|fig(?:ure)?|appendix)\s*"
    r"([A-Z]?\d+(?:\.\d+){0,5})"
)
_BARE_REF = re.compile(r"\b([A-Z]?\d+(?:\.\d+){2,5})\b")
_STANDARD_REF = re.compile(r"\b(AS(?:/NZS)?\s*\d{3,4}(?:\.\d+)*)\b", re.I)


def query_terms(query: str) -> list[str]:
    terms = []
    for match in _TOKEN.finditer(query):
        term = match.group(0).strip("._/+-").lower()
        if not term or len(term) < 2:
            continue
        if term in STOPWORDS and term != "as":
            continue
        if term not in terms:
            terms.append(term)
    return terms[:24]


def clause_refs(query: str) -> list[str]:
    refs = []
    for match in _CLAUSE_REF.finditer(query):
        refs.append(match.group(1))
    for match in _BARE_REF.finditer(query):
        if match.group(1) not in refs:
            refs.append(match.group(1))
    return refs[:8]


def standard_refs(query: str) -> list[str]:
    found = []
    for match in _STANDARD_REF.finditer(query):
        code = re.sub(r"\s+", " ", match.group(1).upper())
        if code not in found:
            found.append(code)
    return found


def search(query: str, limit: int = 12) -> list[dict]:
    init_db()
    terms = query_terms(query)
    if not terms:
        return []
    phrases = [item.strip() for item in _QUOTED.findall(query) if item.strip()]
    pieces = []
    for term in terms:
        safe = term.replace('"', "")
        pieces.append(f'"{safe}"')
    fts_query = " OR ".join(pieces)
    conn = connect()
    try:
        try:
            rows = conn.execute(
                """SELECT c.id, c.doc_id, c.page, c.printed_page, c.section,
                          c.text, d.filename, d.title, d.code, d.edition,
                          bm25(chunks_fts, 1.0, 2.0, 1.5, 1.2) AS rank
                   FROM chunks_fts
                   JOIN chunks c ON c.id = chunks_fts.rowid
                   JOIN docs d ON d.id = c.doc_id
                   WHERE chunks_fts MATCH ?
                   ORDER BY rank
                   LIMIT 60""",
                (fts_query,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    finally:
        conn.close()

    refs = clause_refs(query)
    standards = standard_refs(query)
    lowered = query.lower()
    scored = []
    for row in rows:
        text = row["text"] or ""
        haystack = " ".join(
            filter(None, [row["title"], row["filename"], row["section"], text])
        ).lower()
        score = -float(row["rank"] or 0.0)
        present = sum(1 for term in terms if term in haystack)
        if present == len(terms):
            score += 2.2
        elif present >= max(2, len(terms) // 2):
            score += 0.8
        for phrase in phrases:
            if phrase.lower() in haystack:
                score += 3.0
        if lowered and len(lowered) > 12 and lowered in haystack:
            score += 1.5
        for ref in refs:
            if ref.lower() in (row["section"] or "").lower():
                score += 4.5
            elif re.search(r"(?<!\d)" + re.escape(ref) + r"(?!\d)", text):
                score += 2.5
        for code in standards:
            code_key = re.sub(r"\s+", "", code).lower()
            title_key = re.sub(r"\s+", "", (row["title"] or "") + (row["filename"] or "")).lower()
            if code_key in title_key:
                score += 3.5
        title_key = (row["title"] or "").lower()
        if any(term in title_key for term in terms):
            score += 1.2
        # Contents pages contain every heading and dot leader, so full-text
        # search loves them.  They are useful for navigation but should not
        # outrank the clause that actually answers the question.
        if text.count("....") >= 2 or "contents" in text[:250].lower():
            score -= 6.0
        if row["section"] and len(text) > 250:
            score += 0.8
        scored.append(
            {
                "id": row["id"],
                "doc_id": row["doc_id"],
                "page": row["page"],
                "printed_page": row["printed_page"],
                "section": row["section"],
                "text": text,
                "filename": row["filename"],
                "title": row["title"],
                "code": row["code"],
                "edition": row["edition"],
                "score": round(score, 3),
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    picked = []
    seen = set()
    for item in scored:
        key = (
            item["doc_id"],
            item["section"] or "",
            item["page"],
            item["text"][:120],
        )
        if key in seen:
            continue
        seen.add(key)
        picked.append(item)
        if len(picked) >= limit:
            break
    return picked


def neighbors(chunk_id: int, doc_id: str, radius: int = 1) -> list[dict]:
    if radius < 1:
        return []
    conn = connect()
    try:
        rows = conn.execute(
            """SELECT c.id, c.doc_id, c.page, c.printed_page, c.section,
                      c.text, d.filename, d.title, d.code, d.edition
               FROM chunks c JOIN docs d ON d.id = c.doc_id
               WHERE c.doc_id = ? AND c.id BETWEEN ? AND ?
               ORDER BY c.id""",
            (doc_id, chunk_id - radius, chunk_id + radius),
        ).fetchall()
        return [dict(row) for row in rows if row["id"] != chunk_id]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Library management
# ---------------------------------------------------------------------------

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._()\[\] &+,'-]+")


def safe_filename(name: str) -> str:
    name = Path(str(name or "")).name
    name = unicodedata.normalize("NFKC", name).strip().strip(".")
    name = _SAFE_NAME.sub("_", name)
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = "document"
    stem = Path(name).stem[:160].strip() or "document"
    suffix = Path(name).suffix[:12].lower()
    if suffix not in SUPPORTED:
        raise ValueError("That file type is not supported.")
    return stem + suffix


def save_upload(filename: str, data: bytes, max_bytes: int = 60 * 1024 * 1024) -> Path:
    if len(data) > max_bytes:
        raise ValueError("That file is too large.")
    LIBRARY.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(LIBRARY, 0o700)
    except OSError:
        pass
    name = safe_filename(filename)
    target = LIBRARY / name
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        for number in range(1, 1000):
            candidate = LIBRARY / f"{stem}-{number}{suffix}"
            if not candidate.exists():
                target = candidate
                break
        else:
            raise ValueError("Too many files with that name.")
    handle = tempfile.NamedTemporaryFile(
        dir=str(LIBRARY), prefix=".upload-", delete=False
    )
    try:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.chmod(handle.name, 0o600)
        os.replace(handle.name, target)
    except Exception:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise
    return target


def doc_for_id(doc_id: str) -> dict | None:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def chunk_for_id(chunk_id: int) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            """SELECT c.id, c.doc_id, c.page, c.printed_page, c.section, c.text,
                      d.title, d.filename, d.code, d.edition, d.pages AS total_pages
               FROM chunks c JOIN docs d ON d.id = c.doc_id
               WHERE c.id = ?""",
            (int(chunk_id),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def doc_path(doc: dict) -> Path | None:
    candidate = (LIBRARY / doc["filename"]).resolve()
    try:
        candidate.relative_to(LIBRARY.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def delete_document(doc_id: str) -> bool:
    init_db()
    with IndexLock():
        conn = connect()
        try:
            row = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
            if not row:
                return False
            path = doc_path(dict(row))
            if path:
                trash = LIBRARY / ".trash"
                trash.mkdir(parents=True, exist_ok=True)
                try:
                    os.chmod(trash, 0o700)
                except OSError:
                    pass
                target = trash / f"{int(time.time())}-{path.name}"
                shutil.move(str(path), str(target))
            _delete_doc(conn, doc_id)
            conn.commit()
            return True
        finally:
            conn.close()


def list_docs() -> list[dict]:
    init_db()
    conn = connect()
    try:
        rows = conn.execute(
            """SELECT d.*, COUNT(c.id) AS chunks
               FROM docs d LEFT JOIN chunks c ON c.doc_id = d.id
               GROUP BY d.id ORDER BY d.filename COLLATE NOCASE"""
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def stats() -> dict:
    init_db()
    conn = connect()
    try:
        docs = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(pages),0) AS pages, "
            "COALESCE(SUM(size),0) AS size, COALESCE(SUM(text_chars),0) AS chars "
            "FROM docs WHERE status = 'ok'"
        ).fetchone()
        chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
        errors = conn.execute(
            "SELECT COUNT(*) AS n FROM docs WHERE status = 'error'"
        ).fetchone()
        last = conn.execute(
            "SELECT value FROM meta WHERE key = 'last_sync'"
        ).fetchone()
        library = LIBRARY
        return {
            "docs": docs["n"],
            "pages": docs["pages"],
            "chunks": chunks["n"],
            "text_chars": docs["chars"],
            "size": docs["size"],
            "errors": errors["n"],
            "last_sync": int(last["value"]) if last and last["value"] else None,
            "library": str(library),
            "db": str(DB),
            "db_bytes": DB.stat().st_size if DB.is_file() else 0,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_stats(data: dict) -> None:
    print(f"Library : {data['library']}")
    print(f"Index   : {data['db']} ({data['db_bytes'] / 1024 / 1024:.1f} MB)")
    print(f"Documents: {data['docs']}   Pages: {data['pages']}   Chunks: {data['chunks']}")
    print(f"Text    : {data['text_chars']:,} chars   Errors: {data['errors']}")
    if data.get("last_sync"):
        print("Last sync: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data["last_sync"])))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FitterCalcs local document index")
    sub = parser.add_subparsers(dest="command", required=True)

    sync_parser = sub.add_parser("sync", help="index new and changed documents")
    sync_parser.add_argument("--no-ocr", action="store_true", help="skip OCR on scanned pages")
    sync_parser.add_argument("--ocr-all", action="store_true", help="OCR every page")

    sub.add_parser("list", help="list indexed documents")
    sub.add_parser("stats", help="show index statistics")

    search_parser = sub.add_parser("search", help="search the index")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=8)

    ask_parser = sub.add_parser("ask", help="ask the assistant from the terminal")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--thinking", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "sync":
        init_db()
        try:
            result = sync(
                ocr=not args.no_ocr,
                ocr_all=args.ocr_all,
                progress=lambda done, total, name: print(
                    f"[{done}/{total}] {name}", flush=True
                ),
            )
        except BusyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if not result["errors"] else 1

    if args.command == "list":
        for doc in list_docs():
            print(
                f"{doc['id']}  {doc['filename']}  "
                f"{doc['pages']}p  {doc['chunks']} chunks  {doc['status']}"
            )
        return 0

    if args.command == "stats":
        _print_stats(stats())
        return 0

    if args.command == "search":
        for item in search(args.query, limit=args.limit):
            page = item["printed_page"] or item["page"]
            print(
                f"[{item['score']}] {item['title']} | {item['section'] or ''} "
                f"| p.{page} | {item['filename']}"
            )
            print("    " + re.sub(r"\s+", " ", item["text"])[:280])
        return 0

    if args.command == "ask":
        import assistant
        return assistant.cli_ask(args.question, thinking=args.thinking)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
