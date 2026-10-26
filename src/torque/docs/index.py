"""
A local search index over the folders you choose (SQLite FTS5, BM25 ranking).

Incremental: a file is re-read only when its size or modified time changed, and
files that disappeared are dropped. The index stores text chunks on this PC
(data/docs.db); delete the file to wipe it.
"""

import re
import sqlite3
import threading
from pathlib import Path

from loguru import logger

from torque.docs.reader import SKIP_DIRS, SUPPORTED, is_secret, read_text

CHUNK_CHARS = 900
OVERLAP = 150
MAX_FILES = 20_000
MAX_CHUNKS_PER_FILE = 2_000

_WORD = re.compile(r"[A-Za-z0-9_]{2,}")
STOP = {"the", "and", "for", "with", "that", "this", "what", "which", "about", "does", "did", "say", "says",
        "said", "was", "were", "are", "from", "into", "have", "has", "had", "how", "who", "why", "when", "where",
        "my", "me", "of", "in", "on", "to", "is", "it", "a", "an", "or", "do", "your", "you", "notes", "note",
        "documents", "document", "files", "file", "lecture", "slides", "pdf", "tell", "explain", "find", "search",
        "according", "mention", "mentioned", "talk", "talks"}


def chunk(text: str):
    """Overlapping ~900-character pieces, cut at paragraph/sentence/space boundaries."""

    text = re.sub(r"[ \t]+", " ", text.replace("\r", "")).strip()

    if not text:
        return []

    pieces, start = [], 0

    while start < len(text) and len(pieces) < MAX_CHUNKS_PER_FILE:
        end = min(len(text), start + CHUNK_CHARS)

        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("\n"), window.rfind(" "))

            if cut > CHUNK_CHARS * 0.5:
                end = start + cut + 1

        piece = text[start:end].strip()

        if piece:
            pieces.append(piece)

        if end >= len(text):
            break

        start = max(end - OVERLAP, start + 1)

    return pieces


def query_terms(question: str):
    terms = [w.lower() for w in _WORD.findall(question or "")]

    return [t for t in dict.fromkeys(terms) if t not in STOP]


class DocIndex:

    def __init__(self, db_path=None):
        self._lock = threading.RLock()
        path = Path(db_path) if db_path not in (None, ":memory:") else None

        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(str(path) if path else ":memory:", check_same_thread=False)

        with self._lock:
            try:
                self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5("
                                  "text, path UNINDEXED, loc UNINDEXED, tokenize='porter unicode61')")
            except sqlite3.OperationalError as error:
                raise RuntimeError("This Python's SQLite has no FTS5 support.") from error

            self.conn.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, size INTEGER, mtime REAL, chunks INTEGER)")
            self.conn.commit()

    # ---- indexing ----------------------------------------------------------

    def _walk(self, root: Path):
        for path in root.rglob("*"):
            if len(parts := [p.lower() for p in path.relative_to(root).parts[:-1]]) and any(p in SKIP_DIRS for p in parts):
                continue

            if path.is_file() and path.suffix.lower() in SUPPORTED and not is_secret(path):
                yield path

    def index_folder(self, folder, progress=None, cancel=None) -> dict:
        """Index one folder. Returns {'added', 'updated', 'removed', 'skipped', 'files'}."""

        root = Path(folder).expanduser().resolve()
        stats = {"added": 0, "updated": 0, "removed": 0, "skipped": 0, "files": 0}

        if not root.is_dir():
            raise FileNotFoundError(str(root))

        seen = set()

        for number, path in enumerate(self._walk(root), 1):
            if cancel and cancel():
                break

            if number > MAX_FILES:
                break

            key = str(path)
            seen.add(key)

            try:
                info = path.stat()
            except OSError:
                stats["skipped"] += 1
                continue

            with self._lock:
                row = self.conn.execute("SELECT size, mtime FROM files WHERE path = ?", (key,)).fetchone()

            if row and row[0] == info.st_size and abs(row[1] - info.st_mtime) < 1e-3:
                stats["files"] += 1
                continue

            pages = read_text(path)
            pieces = [(loc, c) for loc, text in pages for c in chunk(text)][:MAX_CHUNKS_PER_FILE]

            if not pieces:
                stats["skipped"] += 1
                continue

            with self._lock:
                self.conn.execute("DELETE FROM chunks WHERE path = ?", (key,))
                self.conn.executemany("INSERT INTO chunks (text, path, loc) VALUES (?, ?, ?)",
                                      [(c, key, loc) for loc, c in pieces])
                self.conn.execute("INSERT OR REPLACE INTO files (path, size, mtime, chunks) VALUES (?, ?, ?, ?)",
                                  (key, info.st_size, info.st_mtime, len(pieces)))
                self.conn.commit()

            stats["updated" if row else "added"] += 1
            stats["files"] += 1

            if progress:
                progress(stats)

        stats["removed"] = self._drop_missing(root, seen) if not (cancel and cancel()) else 0

        return stats

    def _drop_missing(self, root: Path, seen: set) -> int:
        prefix = str(root)

        with self._lock:
            rows = self.conn.execute("SELECT path FROM files WHERE path LIKE ?", (prefix + "%",)).fetchall()
            gone = [r[0] for r in rows if r[0] not in seen and Path(r[0]).is_relative_to(root)]

            for path in gone:
                self.conn.execute("DELETE FROM chunks WHERE path = ?", (path,))
                self.conn.execute("DELETE FROM files WHERE path = ?", (path,))

            self.conn.commit()

        return len(gone)

    def forget_folder(self, folder) -> int:
        root = Path(folder).expanduser().resolve()

        with self._lock:
            paths = [r[0] for r in self.conn.execute("SELECT path FROM files").fetchall()
                     if Path(r[0]).is_relative_to(root)]

            for path in paths:
                self.conn.execute("DELETE FROM chunks WHERE path = ?", (path,))
                self.conn.execute("DELETE FROM files WHERE path = ?", (path,))

            self.conn.commit()

        return len(paths)

    def clear(self):
        with self._lock:
            self.conn.execute("DELETE FROM chunks")
            self.conn.execute("DELETE FROM files")
            self.conn.commit()

    # ---- searching ---------------------------------------------------------

    def stats(self) -> dict:
        with self._lock:
            files, chunks = self.conn.execute("SELECT COUNT(*), COALESCE(SUM(chunks), 0) FROM files").fetchone()

        return {"files": files, "chunks": chunks}

    def search(self, question: str, limit=5, embedder=None):
        """[(path, loc, text, score)] best first. Words are OR-ed: any strong term can find a passage."""

        terms = query_terms(question)

        if not terms:
            return []

        match = " OR ".join(f'"{t}"' for t in terms[:12])

        with self._lock:
            rows = self.conn.execute(
                "SELECT path, loc, text, bm25(chunks) FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT ?",
                (match, limit * 4 if embedder else limit)).fetchall()

        results = [(path, loc, text, -score) for path, loc, text, score in rows]

        if embedder and results:
            results = rerank(embedder, question, results)

        return results[:limit]


def rerank(embedder, question, results):
    """Reorder lexical hits by meaning when an embedder (text -> vector) is available."""

    try:
        vectors = embedder([question] + [r[2] for r in results])
    except Exception:  # noqa: BLE001
        logger.debug("Embedding rerank failed; keeping keyword order.", exc_info=True)
        return results

    import numpy as np

    q = np.asarray(vectors[0], dtype=float)
    scored = []

    for (path, loc, text, lexical), v in zip(results, vectors[1:]):
        v = np.asarray(v, dtype=float)
        sim = float(q @ v / (np.linalg.norm(q) * np.linalg.norm(v) + 1e-12))
        scored.append((path, loc, text, sim))

    return sorted(scored, key=lambda r: -r[3])
