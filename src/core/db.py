"""SQLite persistence for conversations and structured logs."""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_DB_PATH = Path("data/showmeoff.db")

SCHEMA_SQL = """\
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    metadata    TEXT
);

CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conv_created ON conversations(created_at);

CREATE TABLE IF NOT EXISTS logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    level       TEXT NOT NULL,
    event       TEXT NOT NULL,
    session_id  TEXT,
    fields      TEXT
);

CREATE INDEX IF NOT EXISTS idx_logs_session ON logs(session_id);
CREATE INDEX IF NOT EXISTS idx_logs_event   ON logs(event);
CREATE INDEX IF NOT EXISTS idx_logs_ts      ON logs(timestamp);
"""


class Database:
    """Thread-safe SQLite wrapper for conversations and logs."""

    def __init__(self, db_path: str | Path = _DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self):
        conn = self._get_conn()
        conn.executescript(SCHEMA_SQL)
        conn.commit()

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------

    def save_message(self, session_id: str, role: str, content: str,
                     metadata: dict | None = None):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO conversations (session_id, role, content, metadata) "
            "VALUES (?, ?, ?, ?)",
            (session_id, role, content, json.dumps(metadata) if metadata else None),
        )
        conn.commit()

    def get_session_history(self, session_id: str, limit: int = 40) -> list[dict]:
        """Return the most recent messages for a session as [{role, content}, ...]."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT role, content FROM ("
            "  SELECT role, content, id FROM conversations "
            "  WHERE session_id = ? ORDER BY id DESC LIMIT ?"
            ") sub ORDER BY id ASC",
            (session_id, limit),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def list_sessions(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Return session summaries: session_id, first_query, message_count, timestamps."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT session_id, "
            "  MIN(CASE WHEN role='user' THEN content END) AS first_query, "
            "  COUNT(*) AS message_count, "
            "  MIN(created_at) AS started_at, "
            "  MAX(created_at) AS last_at "
            "FROM conversations "
            "GROUP BY session_id "
            "ORDER BY MAX(id) DESC "
            "LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    def session_exists(self, session_id: str) -> bool:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM conversations WHERE session_id = ? LIMIT 1",
            (session_id,),
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    def save_log(self, timestamp: str, level: str, event: str,
                 session_id: str | None = None, fields: dict | None = None):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO logs (timestamp, level, event, session_id, fields) "
            "VALUES (?, ?, ?, ?, ?)",
            (timestamp, level, event, session_id, json.dumps(fields) if fields else None),
        )
        conn.commit()

    def query_logs(self, session_id: str | None = None, event: str | None = None,
                   level: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
        clauses = []
        params: list = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if event:
            clauses.append("event = ?")
            params.append(event)
        if level:
            clauses.append("level = ?")
            params.append(level)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([limit, offset])

        conn = self._get_conn()
        rows = conn.execute(
            f"SELECT * FROM logs{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            if d.get("fields"):
                d["fields"] = json.loads(d["fields"])
            results.append(d)
        return results

    def close(self):
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn
