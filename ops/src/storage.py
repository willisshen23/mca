from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    overall TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runbooks(
    slug TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    body TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS diagnoses(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    check_id TEXT NOT NULL,
    playbook TEXT NOT NULL,
    conclusion TEXT NOT NULL,
    transcript TEXT NOT NULL,
    degraded INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class OpsDB:
    """ops-assistant 自有 SQLite（巡检快照 / runbook / 诊断记录）。"""

    def __init__(self, path):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ---- snapshots ----

    def save_snapshot(self, overall: str, payload: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO snapshots(created_at, overall, payload) VALUES(?,?,?)",
                (_utcnow(), overall, payload),
            )
            self._conn.commit()
            return cur.lastrowid

    def _row_to_snapshot(self, row) -> dict:
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "overall": row["overall"],
            "payload": json.loads(row["payload"]),
        }

    def latest_snapshot(self) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def list_snapshots(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM snapshots ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def purge_snapshots(self, days: int) -> None:
        if days <= 0:
            # days=0 按"刚写入的不删"处理：不清空全部，避免误删
            return
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            self._conn.execute("DELETE FROM snapshots WHERE created_at < ?", (cutoff,))
            self._conn.commit()

    # ---- runbooks ----

    def upsert_runbook(self, slug: str, title: str, category: str, body: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO runbooks(slug,title,category,body,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(slug) DO UPDATE SET title=excluded.title, "
                "category=excluded.category, body=excluded.body, updated_at=excluded.updated_at",
                (slug, title, category, body, _utcnow()),
            )
            self._conn.commit()

    def list_runbooks(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT slug,title,category,updated_at FROM runbooks ORDER BY slug"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_runbook(self, slug: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM runbooks WHERE slug=?", (slug,)
            ).fetchone()
        return dict(row) if row else None

    def get_runbook_by_category(self, category: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM runbooks WHERE category=? ORDER BY slug LIMIT 1", (category,)
            ).fetchone()
        return dict(row) if row else None

    def seed_runbooks(self, seed_dir) -> int:
        seed_dir = Path(seed_dir)
        if not seed_dir.is_dir():
            return 0
        imported = 0
        for md in sorted(seed_dir.glob("*.md")):
            text = md.read_text(encoding="utf-8")
            title = text.splitlines()[0].lstrip("# ").strip() if text.strip() else md.stem
            with self._lock:
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO runbooks(slug,title,category,body,updated_at) "
                    "VALUES(?,?,?,?,?)",
                    (md.stem, title, md.stem, text, _utcnow()),
                )
                self._conn.commit()
            imported += cur.rowcount
        return imported

    # ---- diagnoses ----

    def save_diagnosis(self, check_id, playbook, conclusion, transcript, degraded, error) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO diagnoses(created_at,check_id,playbook,conclusion,transcript,"
                "degraded,error) VALUES(?,?,?,?,?,?,?)",
                (_utcnow(), check_id, playbook, conclusion, transcript, int(degraded), error),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_diagnosis(self, diagnosis_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM diagnoses WHERE id=?", (diagnosis_id,)
            ).fetchone()
        return dict(row) if row else None

    def append_message(self, diagnosis_id: int, role: str, content: str) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT transcript FROM diagnoses WHERE id=?", (diagnosis_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"diagnosis {diagnosis_id} 不存在")
            transcript = json.loads(row["transcript"])
            transcript.append({"role": role, "content": content})
            self._conn.execute(
                "UPDATE diagnoses SET transcript=? WHERE id=?",
                (json.dumps(transcript, ensure_ascii=False), diagnosis_id),
            )
            self._conn.commit()
