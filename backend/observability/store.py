"""SQLite storage for one summarized row per request (chat or quiz).

Raw spans go to Jaeger. This table keeps only the numbers the dashboard needs so
it doesn't have to query Jaeger on every page load.
"""
import json
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    trace_id       TEXT PRIMARY KEY,
    created_at     REAL NOT NULL,
    kind           TEXT NOT NULL DEFAULT 'chat',
    question       TEXT,
    status         TEXT NOT NULL,
    error          TEXT,
    total_ms       REAL NOT NULL,
    ttft_ms        REAL,
    steps_json     TEXT NOT NULL,
    model          TEXT,
    input_tokens   INTEGER NOT NULL DEFAULT 0,
    output_tokens  INTEGER NOT NULL DEFAULT 0,
    cost_usd       REAL NOT NULL DEFAULT 0,
    groundedness   REAL
);
"""


class RequestStore:
    def __init__(self, path: Path | str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(SCHEMA)
        self._conn.commit()

    def add(self, row: dict) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO requests VALUES
                (:trace_id, :created_at, :kind, :question, :status, :error, :total_ms,
                 :ttft_ms, :steps_json, :model, :input_tokens, :output_tokens, :cost_usd,
                 :groundedness)""",
                {**row, "steps_json": json.dumps(row["steps"])},
            )
            self._conn.commit()

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM requests ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["steps"] = json.loads(d.pop("steps_json"))
            out.append(d)
        return out

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM requests")
            self._conn.commit()
