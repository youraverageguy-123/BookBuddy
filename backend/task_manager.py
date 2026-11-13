"""Persistent, reader-safe metadata for recoverable background work.

The queue records lifecycle and recovery intent. Existing analyzers retain their
staging/atomic-promotion contracts; this module never writes canonical graph data.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

TERMINAL_TASK_STATES = {"succeeded", "failed", "cancelled"}
ACTIVE_TASK_STATES = {"queued", "running", "cancelling", "paused"}
TASK_TYPES = {"analysis", "ocr", "image", "web", "translation", "replay", "search_index", "cover"}
TASK_RETENTION_SECONDS = 30 * 24 * 60 * 60
TASK_TERMINAL_LIMIT = 500


class PersistentTaskManager:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self.recover_stale_tasks()
        self.prune_terminal_tasks()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _table_sql(name: str = "background_tasks") -> str:
        return f"""CREATE TABLE {name} (
            task_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL,
            task_type TEXT NOT NULL, session_key TEXT NOT NULL DEFAULT '', chapter_index INTEGER,
            priority INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
            stage TEXT NOT NULL DEFAULT '', retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3, retryable INTEGER NOT NULL DEFAULT 1,
            cancel_requested INTEGER NOT NULL DEFAULT 0, cancel_acknowledged INTEGER NOT NULL DEFAULT 0,
            worker_lease_until REAL, lease_owner TEXT,
            diagnostic_code TEXT, user_message TEXT NOT NULL DEFAULT '', payload_json TEXT NOT NULL DEFAULT '{{}}',
            created_at REAL NOT NULL, queued_at REAL, started_at REAL, cancel_requested_at REAL,
            cancel_acknowledged_at REAL, finished_at REAL, updated_at REAL NOT NULL
        )"""

    def _backup_for_migration(self, migration_id: str) -> Path | None:
        if not self.path.is_file() or self.path.stat().st_size == 0:
            return None
        backup_path = self.path.with_name(f"{self.path.name}.pre-{migration_id}.bak")
        if backup_path.is_file():
            return backup_path
        temporary = backup_path.with_name(f".{backup_path.name}.{uuid.uuid4().hex}.tmp")
        source = sqlite3.connect(self.path)
        destination = sqlite3.connect(temporary)
        try:
            source.backup(destination)
            if destination.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("task database backup failed quick_check")
            destination.commit()
        finally:
            destination.close()
            source.close()
        os.replace(temporary, backup_path)
        return backup_path

    def _initialize(self) -> None:
        migration_id = "task_active_idempotency_v1"
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS task_schema_migrations (migration_id TEXT PRIMARY KEY, applied_at REAL NOT NULL, backup_path TEXT)")
            table = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='background_tasks'").fetchone()
        if table is None:
            with self._connect() as conn:
                conn.execute(self._table_sql())
        else:
            existing_sql = str(table["sql"] or "").upper()
            needs_rebuild = "IDEMPOTENCY_KEY TEXT NOT NULL UNIQUE" in existing_sql
            if needs_rebuild:
                backup = self._backup_for_migration(migration_id)
                with self._connect() as conn:
                    conn.execute("PRAGMA foreign_keys=OFF")
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("DROP TABLE IF EXISTS background_tasks_migrating")
                    conn.execute(self._table_sql("background_tasks_migrating"))
                    conn.execute("""INSERT INTO background_tasks_migrating (
                        task_id,idempotency_key,task_type,session_key,chapter_index,priority,state,progress,
                        stage,retry_count,max_retries,retryable,cancel_requested,worker_lease_until,
                        diagnostic_code,user_message,payload_json,created_at,queued_at,updated_at
                    ) SELECT task_id,idempotency_key,task_type,session_key,chapter_index,priority,state,progress,
                        stage,retry_count,max_retries,retryable,cancel_requested,worker_lease_until,
                        diagnostic_code,user_message,payload_json,created_at,created_at,updated_at
                    FROM background_tasks""")
                    old_count = conn.execute("SELECT COUNT(*) FROM background_tasks").fetchone()[0]
                    new_count = conn.execute("SELECT COUNT(*) FROM background_tasks_migrating").fetchone()[0]
                    if old_count != new_count:
                        raise RuntimeError("task migration row-count verification failed")
                    conn.execute("DROP TABLE background_tasks")
                    conn.execute("ALTER TABLE background_tasks_migrating RENAME TO background_tasks")
                    if conn.execute("PRAGMA foreign_key_check").fetchall():
                        raise RuntimeError("task migration foreign_key_check failed")
                    if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise RuntimeError("task migration quick_check failed")
                    conn.execute(
                        "INSERT OR REPLACE INTO task_schema_migrations(migration_id,applied_at,backup_path) VALUES(?,?,?)",
                        (migration_id, time.time(), str(backup) if backup else None),
                    )
                    conn.commit()
                    conn.execute("PRAGMA foreign_keys=ON")
            else:
                required_columns = {
                    "cancel_acknowledged": "INTEGER NOT NULL DEFAULT 0",
                    "lease_owner": "TEXT",
                    "queued_at": "REAL",
                    "started_at": "REAL",
                    "cancel_requested_at": "REAL",
                    "cancel_acknowledged_at": "REAL",
                    "finished_at": "REAL",
                }
                with self._connect() as conn:
                    columns = {row["name"] for row in conn.execute("PRAGMA table_info(background_tasks)")}
                    for name, definition in required_columns.items():
                        if name not in columns:
                            conn.execute(f"ALTER TABLE background_tasks ADD COLUMN {name} {definition}")
        with self._connect() as conn:
            conn.execute("CREATE INDEX IF NOT EXISTS background_tasks_state ON background_tasks(state, priority DESC, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS background_tasks_session ON background_tasks(session_key, updated_at DESC)")
            conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS background_tasks_active_idempotency
                ON background_tasks(idempotency_key)
                WHERE state IN ('queued','running','cancelling','paused')""")

    @staticmethod
    def _row(row: sqlite3.Row) -> dict:
        value = dict(row)
        value["retryable"] = bool(value["retryable"])
        value["cancel_requested"] = bool(value["cancel_requested"])
        value["cancel_acknowledged"] = bool(value.get("cancel_acknowledged", 0))
        value["payload"] = json.loads(value.pop("payload_json") or "{}")
        return value

    def enqueue(self, task_type: str, idempotency_key: str, session_key: str = "", chapter_index: int | None = None, priority: int = 0, payload: dict | None = None, max_retries: int = 3) -> dict:
        if task_type not in TASK_TYPES: raise ValueError("unsupported task type")
        self.prune_terminal_tasks()
        now = time.time(); task_id = str(uuid.uuid4())
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM background_tasks WHERE idempotency_key=? AND state IN ('queued','running','cancelling','paused') ORDER BY created_at DESC LIMIT 1", (idempotency_key,)).fetchone()
            if existing:
                return self._row(existing)
            try:
                conn.execute("INSERT INTO background_tasks(task_id,idempotency_key,task_type,session_key,chapter_index,priority,state,max_retries,payload_json,created_at,queued_at,updated_at,user_message) VALUES(?,?,?,?,?,?, 'queued',?,?,?,?,?,?)", (task_id,idempotency_key,task_type,session_key,chapter_index,priority,max_retries,json.dumps(payload or {},sort_keys=True),now,now,now,"Queued"))
            except sqlite3.IntegrityError:
                existing = conn.execute("SELECT * FROM background_tasks WHERE idempotency_key=? AND state IN ('queued','running','cancelling','paused') ORDER BY created_at DESC LIMIT 1", (idempotency_key,)).fetchone()
                if existing:
                    return self._row(existing)
                raise
            row = conn.execute("SELECT * FROM background_tasks WHERE task_id=?", (task_id,)).fetchone()
        return self._row(row)

    def update(self, task_id: str, *, state: str | None = None, progress: float | None = None, stage: str | None = None, diagnostic_code: str | None = None, user_message: str | None = None, lease_seconds: float | None = None, lease_owner: str | None = None, cancel_acknowledged: bool | None = None) -> dict:
        fields = ["updated_at=?"]; values: list[object] = [time.time()]
        for name, value in (("state",state),("progress",progress),("stage",stage),("diagnostic_code",diagnostic_code),("user_message",user_message)):
            if value is not None: fields.append(f"{name}=?"); values.append(max(0,min(100,float(value))) if name == "progress" else value)
        if lease_seconds is not None: fields.append("worker_lease_until=?"); values.append(time.time()+max(1,lease_seconds))
        if lease_owner is not None: fields.append("lease_owner=?"); values.append(lease_owner)
        if cancel_acknowledged is not None:
            fields.extend(["cancel_acknowledged=?", "cancel_acknowledged_at=CASE WHEN ? THEN COALESCE(cancel_acknowledged_at,?) ELSE cancel_acknowledged_at END"])
            values.extend([int(cancel_acknowledged), int(cancel_acknowledged), time.time()])
        if state == "running":
            fields.append("started_at=COALESCE(started_at,?)"); values.append(time.time())
        if state in TERMINAL_TASK_STATES:
            fields.extend(["finished_at=?", "worker_lease_until=NULL", "lease_owner=NULL"]); values.append(time.time())
        values.append(task_id)
        with self._connect() as conn:
            cursor = conn.execute(f"UPDATE background_tasks SET {', '.join(fields)} WHERE task_id=?", values)
            if not cursor.rowcount: raise LookupError("task not found")
            row = conn.execute("SELECT * FROM background_tasks WHERE task_id=?", (task_id,)).fetchone()
        return self._row(row)

    def list(self, state: str | None = None, session_key: str | None = None) -> list[dict]:
        sql = "SELECT * FROM background_tasks WHERE 1=1"; values: list[object] = []
        if state: sql += " AND state=?"; values.append(state)
        if session_key: sql += " AND session_key=?"; values.append(session_key)
        sql += " ORDER BY CASE state WHEN 'running' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END, priority DESC, updated_at DESC LIMIT 1000"
        with self._connect() as conn: return [self._row(row) for row in conn.execute(sql, values)]

    def get(self, task_id: str) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM background_tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            raise LookupError("task not found")
        return self._row(row)

    def request_cancel(self, task_id: str) -> dict:
        now = time.time()
        with self._connect() as conn:
            cursor = conn.execute("""UPDATE background_tasks
                SET cancel_requested=1, state='cancelling', cancel_requested_at=COALESCE(cancel_requested_at,?),
                    user_message='Cancellation requested', updated_at=?
                WHERE task_id=? AND state IN ('queued','running','cancelling','paused')""", (now,now,task_id))
            if not cursor.rowcount: raise LookupError("active task not found")
            row = conn.execute("SELECT * FROM background_tasks WHERE task_id=?", (task_id,)).fetchone()
        return self._row(row)

    def request_pause(self, task_id: str) -> dict:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE background_tasks SET state='paused', user_message='Paused before execution', updated_at=? WHERE task_id=? AND state='queued'",
                (time.time(), task_id),
            )
            if not cursor.rowcount:
                raise ValueError("Only queued tasks can be paused safely")
            row = conn.execute("SELECT * FROM background_tasks WHERE task_id=?", (task_id,)).fetchone()
        return self._row(row)

    def resume(self, task_id: str) -> dict:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE background_tasks SET state='queued', queued_at=?, user_message='Queued after pause', updated_at=? WHERE task_id=? AND state='paused'",
                (time.time(), time.time(), task_id),
            )
            if not cursor.rowcount:
                raise ValueError("Only paused tasks can be resumed")
            row = conn.execute("SELECT * FROM background_tasks WHERE task_id=?", (task_id,)).fetchone()
        return self._row(row)

    def acknowledge_cancel(self, task_id: str) -> dict:
        return self.update(task_id, cancel_acknowledged=True, user_message="Cancellation acknowledged; stopping safely")

    def mark_cancelled(self, task_id: str) -> dict:
        return self.update(task_id, state="cancelled", cancel_acknowledged=True, user_message="Cancelled safely")

    def cancel_requested(self, task_id: str) -> bool:
        return bool(self.get(task_id)["cancel_requested"])

    def active_for_session(self, session_key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM background_tasks WHERE session_key=? AND state IN ('queued','running','cancelling','paused') ORDER BY created_at DESC LIMIT 1", (session_key,)).fetchone()
        return self._row(row) if row else None

    def retry(self, task_id: str) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM background_tasks WHERE task_id=?", (task_id,)).fetchone()
            if not row: raise LookupError("task not found")
            if row["state"] in {"queued", "running", "cancelling", "paused", "succeeded"}: raise ValueError("task cannot be retried in its current state")
            if not row["retryable"] or row["retry_count"] >= row["max_retries"]: raise ValueError("task cannot be retried")
            now = time.time()
            conn.execute("UPDATE background_tasks SET state='queued',progress=0,stage='',diagnostic_code=NULL,cancel_requested=0,cancel_acknowledged=0,cancel_requested_at=NULL,cancel_acknowledged_at=NULL,finished_at=NULL,queued_at=?,retry_count=retry_count+1,user_message='Queued for retry',updated_at=? WHERE task_id=?", (now,now,task_id))
            row = conn.execute("SELECT * FROM background_tasks WHERE task_id=?", (task_id,)).fetchone()
        return self._row(row)

    def recover_stale_tasks(self) -> int:
        now = time.time()
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE background_tasks
                   SET state='failed', worker_lease_until=NULL, lease_owner=NULL, finished_at=?,
                       diagnostic_code='restart_interrupted',
                       user_message='Interrupted by restart; run the original action again',
                       updated_at=?
                   WHERE state IN ('queued','running','cancelling')""",
                (now,now),
            )
            return cursor.rowcount

    def prune_terminal_tasks(self, retention_seconds: float = TASK_RETENTION_SECONDS, maximum: int = TASK_TERMINAL_LIMIT) -> int:
        cutoff = time.time() - max(0.0, float(retention_seconds))
        maximum = max(0, int(maximum))
        with self._connect() as conn:
            removed = conn.execute("DELETE FROM background_tasks WHERE state IN ('succeeded','failed','cancelled') AND updated_at < ?", (cutoff,)).rowcount
            removed += conn.execute("""DELETE FROM background_tasks WHERE task_id IN (
                SELECT task_id FROM background_tasks WHERE state IN ('succeeded','failed','cancelled')
                ORDER BY updated_at DESC LIMIT -1 OFFSET ?
            )""", (maximum,)).rowcount
        return removed

    def quick_check(self) -> str:
        with self._connect() as conn: return str(conn.execute("PRAGMA quick_check").fetchone()[0])
