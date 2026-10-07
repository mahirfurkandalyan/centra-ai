"""SQLite tabanlı SSS deposu + bellekte tutulan vektör indeksi."""
import re
import sqlite3
import threading
from datetime import datetime

import numpy as np

from . import config
from .parser import FaqEntry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS faqs (
    id           INTEGER PRIMARY KEY,
    question     TEXT NOT NULL,
    question_key TEXT NOT NULL UNIQUE,
    module       TEXT NOT NULL,
    answer       TEXT NOT NULL,
    embedding    BLOB,
    source_file  TEXT,
    source_type  TEXT NOT NULL DEFAULT 'gap',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_logs (
    id         INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    question   TEXT NOT NULL,
    answer     TEXT NOT NULL,
    mode       TEXT NOT NULL,
    score      REAL,
    faq_id     INTEGER,
    latency_ms INTEGER
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Aynı soru birden fazla kaynakta varsa yüksek öncelikli olan kalır.
# gap: QA hattında düzeltilmiş cevap, golden: test için yazılmış referans cevap
SOURCE_PRIORITY = {"golden": 1, "gap": 2}

_index_lock = threading.Lock()
_index: tuple[int, np.ndarray, list[int]] | None = None  # (sürüm, vektör matrisi, faq id'leri)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(_SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(faqs)")}
        if "source_type" not in cols:
            conn.execute("ALTER TABLE faqs ADD COLUMN source_type TEXT NOT NULL DEFAULT 'gap'")


def question_key(question: str) -> str:
    """Yazım farklarını (büyük/küçük harf, noktalama, boşluk) yok sayan anahtar."""
    q = question.replace("I", "ı").replace("İ", "i").casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", q).split())


def _bump_index_version(conn: sqlite3.Connection) -> None:
    """İndeks sürümünü artırır; içe aktarma aracı gibi başka süreçlerin değişikliklerini de yakalar."""
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('index_version', '1')"
        " ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + 1"
    )


def _index_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM meta WHERE key = 'index_version'").fetchone()
    return int(row["value"]) if row else 0


def upsert_faqs(entries: list[FaqEntry], source_file: str, source_type: str = "gap") -> dict:
    stats = {"added": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    priority = SOURCE_PRIORITY[source_type]
    now = _now()
    with connect() as conn:
        for e in entries:
            key = question_key(e.question)
            row = conn.execute(
                "SELECT id, question, module, answer, source_type FROM faqs WHERE question_key = ?", (key,)
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO faqs (question, question_key, module, answer, source_file, source_type,"
                    " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (e.question, key, e.module, e.answer, source_file, source_type, now, now),
                )
                stats["added"] += 1
            elif SOURCE_PRIORITY.get(row["source_type"], 0) > priority:
                stats["skipped"] += 1
            elif (row["question"], row["module"], row["answer"], row["source_type"]) != (
                e.question, e.module, e.answer, source_type
            ):
                # Vektör sorudan üretildiği için soru metni değiştiyse yeniden hesaplanır
                conn.execute(
                    "UPDATE faqs SET question = ?, module = ?, answer = ?, source_file = ?, source_type = ?,"
                    " updated_at = ?, embedding = CASE WHEN question = ? THEN embedding ELSE NULL END"
                    " WHERE id = ?",
                    (e.question, e.module, e.answer, source_file, source_type, now, e.question, row["id"]),
                )
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1
        _bump_index_version(conn)
    return stats


def pending_embeddings(limit: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, question FROM faqs WHERE embedding IS NULL LIMIT ?", (limit,)
        ).fetchall()


def save_embeddings(ids: list[int], vecs: np.ndarray) -> None:
    with connect() as conn:
        conn.executemany(
            "UPDATE faqs SET embedding = ? WHERE id = ?",
            [(v.astype(np.float32).tobytes(), i) for i, v in zip(ids, vecs)],
        )
        _bump_index_version(conn)


def _load_index() -> tuple[np.ndarray, list[int]]:
    global _index
    with _index_lock, connect() as conn:
        version = _index_version(conn)
        if _index is None or _index[0] != version:
            rows = conn.execute("SELECT id, embedding FROM faqs WHERE embedding IS NOT NULL").fetchall()
            ids = [r["id"] for r in rows]
            mat = (
                np.vstack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
                if rows
                else np.zeros((0, 1), dtype=np.float32)
            )
            _index = (version, mat, ids)
        return _index[1], _index[2]


def search(query_vec: np.ndarray, k: int) -> list[tuple[dict, float]]:
    mat, ids = _load_index()
    if not ids:
        return []
    scores = mat @ query_vec
    top = np.argsort(-scores)[:k]
    with connect() as conn:
        results = []
        for idx in top:
            row = conn.execute(
                "SELECT id, question, module, answer FROM faqs WHERE id = ?", (ids[idx],)
            ).fetchone()
            if row:
                results.append((dict(row), float(scores[idx])))
    return results


def list_faqs(q: str = "", module: str = "", limit: int = 100, offset: int = 0) -> dict:
    where, params = [], []
    if q:
        where.append("(question LIKE ? OR answer LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if module:
        where.append("module = ?")
        params.append(module)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM faqs {clause}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT id, question, module, answer, source_type, embedding IS NOT NULL AS indexed, updated_at"
            f" FROM faqs {clause} ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "items": [dict(r) for r in rows]}


def delete_faq(faq_id: int) -> bool:
    with connect() as conn:
        deleted = conn.execute("DELETE FROM faqs WHERE id = ?", (faq_id,)).rowcount > 0
        _bump_index_version(conn)
    return deleted


def stats() -> dict:
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM faqs").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM faqs WHERE embedding IS NULL").fetchone()[0]
        modules = conn.execute(
            "SELECT module, COUNT(*) AS n FROM faqs GROUP BY module ORDER BY n DESC"
        ).fetchall()
        modes = conn.execute("SELECT mode, COUNT(*) AS n FROM chat_logs GROUP BY mode").fetchall()
        sources = conn.execute("SELECT source_type, COUNT(*) AS n FROM faqs GROUP BY source_type").fetchall()
    return {
        "faq_total": total,
        "sources": {r["source_type"]: r["n"] for r in sources},
        "faq_pending_index": pending,
        "modules": [dict(r) for r in modules],
        "chat_modes": {r["mode"]: r["n"] for r in modes},
    }


def log_chat(question: str, answer: str, mode: str, score: float | None, faq_id: int | None, latency_ms: int) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO chat_logs (created_at, question, answer, mode, score, faq_id, latency_ms)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), question, answer, mode, score, faq_id, latency_ms),
        )


def recent_logs(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
