from __future__ import annotations

from dataclasses import asdict
import json
import os
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from .domain import ScanEvent, ScanSession


SCHEMA_VERSION = 2


class SafeStorage:
    """Atomic storage under ProgramData; update packages never own this directory."""

    def __init__(self, root: Path | None = None):
        base = root or Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "TACO"
        self.root = Path(base).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def write_json(self, relative: str, value: object) -> None:
        target = self._target(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=target.name, suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def read_json(self, relative: str, default=None):
        target = self._target(relative)
        if not target.exists():
            return default
        return json.loads(target.read_text(encoding="utf-8"))

    def _target(self, relative: str) -> Path:
        if Path(relative).is_absolute():
            raise ValueError("SafeStorage 只接受相對路徑")
        target = (self.root / relative).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("拒絕存取 ProgramData/TACO 以外的路徑")
        return target


def _connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=10)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    return db


@contextmanager
def _transaction(path: Path):
    db = _connect(path)
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize_integration_db(path: Path) -> None:
    """Additive V6.9 migration; preserves V6.6 Mapping and queue data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = _connect(path)
    try:
        db.execute("PRAGMA journal_mode=WAL").fetchone()
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_info(
              component TEXT PRIMARY KEY, version INTEGER NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS scan_events(
              event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, actor_id TEXT NOT NULL,
              stage TEXT NOT NULL, barcode TEXT NOT NULL, created_at REAL NOT NULL,
              event_type TEXT NOT NULL DEFAULT 'barcode_scanned');
            CREATE INDEX IF NOT EXISTS idx_scan_events_session ON scan_events(session_id, created_at);
            CREATE TABLE IF NOT EXISTS sync_queue(
              event_id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
              attempts INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS mapping_profiles(
              profile_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, mapping_json TEXT NOT NULL,
              updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS inventory_outbox(
              event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL,
              state TEXT NOT NULL CHECK(state IN ('pending','committed','failed')),
              receipt_id TEXT, failure_code TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS update_history(
              update_id TEXT PRIMARY KEY, from_version TEXT NOT NULL, to_version TEXT NOT NULL,
              state TEXT NOT NULL, detail TEXT NOT NULL, created_at REAL NOT NULL);
            """
        )
        columns = {row[1] for row in db.execute("PRAGMA table_info(scan_events)")}
        if "event_type" not in columns:
            db.execute("ALTER TABLE scan_events ADD COLUMN event_type TEXT NOT NULL DEFAULT 'barcode_scanned'")
        db.execute(
            "INSERT INTO schema_info(component,version,updated_at) VALUES('integration',?,?) "
            "ON CONFLICT(component) DO UPDATE SET version=excluded.version, updated_at=excluded.updated_at",
            (SCHEMA_VERSION, time.time()),
        )
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("integration.db quick_check 失敗")
        db.commit()
    finally:
        db.close()


class IntegrationEventStore:
    def __init__(self, path: Path):
        self.path = path
        initialize_integration_db(path)

    def record_scan(self, event: ScanEvent) -> None:
        with _transaction(self.path) as db:
            db.execute(
                "INSERT OR IGNORE INTO scan_events(event_id,session_id,actor_id,stage,barcode,created_at,event_type) "
                "VALUES(?,?,?,?,?,?,?)",
                (event.event_id, event.session_id, event.actor_id, event.stage, event.barcode,
                 event.created_at, event.event_type),
            )

    def append_pending(self, session: ScanSession) -> str:
        event_id = f"receipt:{session.session_id}"
        payload = json.dumps(asdict(session), ensure_ascii=False, default=str, sort_keys=True)
        now = time.time()
        with _transaction(self.path) as db:
            db.execute(
                "INSERT OR IGNORE INTO inventory_outbox"
                "(event_id,session_id,payload,state,created_at,updated_at) VALUES(?,?,?,'pending',?,?)",
                (event_id, session.session_id, payload, now, now),
            )
        return event_id

    def mark_committed(self, event_id: str, receipt_id: str) -> None:
        self._transition(event_id, "committed", receipt_id=receipt_id)

    def mark_failed(self, event_id: str, reason: str) -> None:
        self._transition(event_id, "failed", failure_code=reason[:100])

    def _transition(self, event_id: str, state: str, receipt_id=None, failure_code=None) -> None:
        with _transaction(self.path) as db:
            cursor = db.execute(
                "UPDATE inventory_outbox SET state=?,receipt_id=?,failure_code=?,updated_at=? WHERE event_id=?",
                (state, receipt_id, failure_code, time.time(), event_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(event_id)

    def outbox_state(self, session_id: str) -> str | None:
        with _transaction(self.path) as db:
            row = db.execute("SELECT state FROM inventory_outbox WHERE session_id=?", (session_id,)).fetchone()
        return row[0] if row else None
