"""Transactional SQLite storage for audit, telemetry, idempotency, cache, and profiles."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import threading
import weakref
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .constants import STORAGE_SCHEMA_VERSION
from .errors import StorageError
from .models import AuditRecord, OptimizationProfile, TelemetryRecord

_MIGRATION = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  execution_id TEXT NOT NULL UNIQUE,
  record_json TEXT NOT NULL,
  previous_hash TEXT,
  record_hash TEXT
);
CREATE TABLE IF NOT EXISTS telemetry (
  execution_id TEXT NOT NULL,
  tool_fingerprint TEXT NOT NULL,
  environment TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  record_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS telemetry_tool_idx
  ON telemetry(tool_fingerprint, environment, timestamp);
CREATE TABLE IF NOT EXISTS idempotency (
  tool_fingerprint TEXT NOT NULL,
  identity_scope TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  result_json TEXT NOT NULL,
  PRIMARY KEY(tool_fingerprint, identity_scope, idempotency_key)
);
CREATE TABLE IF NOT EXISTS cache (
  cache_key TEXT PRIMARY KEY,
  expires_at REAL NOT NULL,
  value_json TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  tool_fingerprint TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
  tool_fingerprint TEXT NOT NULL,
  environment TEXT NOT NULL,
  profile_json TEXT NOT NULL,
  PRIMARY KEY(tool_fingerprint, environment)
);
"""


class SQLiteStorage:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._closed = False
        self._finalizer = weakref.finalize(self, self._connection.close)
        self._migrate()

    def _migrate(self) -> None:
        try:
            with self._lock, self._connection:
                self._connection.executescript(_MIGRATION)
                row = self._connection.execute(
                    "SELECT version FROM schema_version LIMIT 1"
                ).fetchone()
                if row is None:
                    self._connection.execute(
                        "INSERT INTO schema_version(version) VALUES (?)", (STORAGE_SCHEMA_VERSION,)
                    )
                elif row["version"] != STORAGE_SCHEMA_VERSION:
                    raise StorageError(
                        f"Unsupported storage schema {row['version']}; "
                        f"expected {STORAGE_SCHEMA_VERSION}"
                    )
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to initialize SQLite storage: {exc}") from exc

    def _ensure_open(self) -> None:
        if self._closed:
            raise StorageError("Storage is closed")

    async def close(self) -> None:
        await asyncio.to_thread(self._close)

    def _close(self) -> None:
        with self._lock:
            if not self._closed:
                self._finalizer()
                self._closed = True

    def __del__(self) -> None:
        if not getattr(self, "_closed", True):
            self._finalizer()
            self._closed = True

    async def append_audit(self, record: AuditRecord, *, hash_chain: bool = True) -> AuditRecord:
        return await asyncio.to_thread(self._append_audit, record, hash_chain)

    def _append_audit(self, record: AuditRecord, hash_chain: bool) -> AuditRecord:
        self._ensure_open()
        with self._lock, self._connection:
            previous = self._connection.execute(
                "SELECT record_hash FROM audit ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous_hash = previous["record_hash"] if previous and hash_chain else None
            base = record.model_copy(update={"previous_hash": previous_hash, "record_hash": None})
            payload = base.model_dump_json(exclude_none=True)
            record_hash = (
                hashlib.sha256(f"{previous_hash or ''}{payload}".encode()).hexdigest()
                if hash_chain
                else None
            )
            final = base.model_copy(update={"record_hash": record_hash})
            cursor = self._connection.execute(
                "INSERT INTO audit(execution_id, record_json, previous_hash, record_hash) "
                "VALUES (?, ?, ?, ?)",
                (record.execution_id, final.model_dump_json(), previous_hash, record_hash),
            )
            return final.model_copy(update={"sequence": cursor.lastrowid})

    async def list_audit(self, limit: int = 100) -> list[AuditRecord]:
        return await asyncio.to_thread(self._list_audit, limit)

    def _list_audit(self, limit: int) -> list[AuditRecord]:
        self._ensure_open()
        with self._lock:
            rows = self._connection.execute(
                "SELECT sequence, record_json FROM audit ORDER BY sequence DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            AuditRecord.model_validate(
                {**json.loads(row["record_json"]), "sequence": row["sequence"]}
            )
            for row in rows
        ]

    async def verify_audit_chain(self) -> bool:
        return await asyncio.to_thread(self._verify_audit_chain)

    def _verify_audit_chain(self) -> bool:
        previous_hash: str | None = None
        with self._lock:
            rows = self._connection.execute(
                "SELECT record_json, previous_hash, record_hash FROM audit ORDER BY sequence"
            ).fetchall()
        for row in rows:
            if row["previous_hash"] != previous_hash:
                return False
            record = AuditRecord.model_validate_json(row["record_json"])
            payload = record.model_copy(update={"record_hash": None}).model_dump_json(
                exclude_none=True
            )
            expected = hashlib.sha256(f"{previous_hash or ''}{payload}".encode()).hexdigest()
            if row["record_hash"] != expected:
                return False
            previous_hash = row["record_hash"]
        return True

    async def add_telemetry(self, record: TelemetryRecord) -> None:
        await asyncio.to_thread(self._add_telemetry, record)

    def _add_telemetry(self, record: TelemetryRecord) -> None:
        self._ensure_open()
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO telemetry VALUES (?, ?, ?, ?, ?)",
                (
                    record.execution_id,
                    record.tool_fingerprint,
                    record.environment,
                    record.timestamp.isoformat(),
                    record.model_dump_json(),
                ),
            )

    async def telemetry_for(self, fingerprint: str, environment: str) -> list[TelemetryRecord]:
        return await asyncio.to_thread(self._telemetry_for, fingerprint, environment)

    def _telemetry_for(self, fingerprint: str, environment: str) -> list[TelemetryRecord]:
        self._ensure_open()
        with self._lock:
            rows = self._connection.execute(
                "SELECT record_json FROM telemetry "
                "WHERE tool_fingerprint=? AND environment=? ORDER BY timestamp",
                (fingerprint, environment),
            ).fetchall()
        return [TelemetryRecord.model_validate_json(row["record_json"]) for row in rows]

    async def get_idempotent(
        self, fingerprint: str, identity: str, key: str
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_idempotent, fingerprint, identity, key)

    def _get_idempotent(self, fingerprint: str, identity: str, key: str) -> dict[str, Any] | None:
        self._ensure_open()
        with self._lock:
            row = self._connection.execute(
                "SELECT result_json FROM idempotency WHERE tool_fingerprint=? "
                "AND identity_scope=? AND idempotency_key=?",
                (fingerprint, identity, key),
            ).fetchone()
        return json.loads(row["result_json"]) if row else None

    async def save_idempotent(
        self, fingerprint: str, identity: str, key: str, result: dict[str, Any]
    ) -> None:
        await asyncio.to_thread(self._save_idempotent, fingerprint, identity, key, result)

    def _save_idempotent(
        self, fingerprint: str, identity: str, key: str, result: dict[str, Any]
    ) -> None:
        self._ensure_open()
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO idempotency VALUES (?, ?, ?, ?)",
                (fingerprint, identity, key, json.dumps(result, sort_keys=True, default=str)),
            )

    async def save_profile(self, profile: OptimizationProfile) -> None:
        await asyncio.to_thread(self._save_profile, profile)

    def _save_profile(self, profile: OptimizationProfile) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO profiles VALUES (?, ?, ?)",
                (profile.tool_fingerprint, profile.environment, profile.model_dump_json()),
            )

    async def get_profile(self, fingerprint: str, environment: str) -> OptimizationProfile | None:
        return await asyncio.to_thread(self._get_profile, fingerprint, environment)

    def _get_profile(self, fingerprint: str, environment: str) -> OptimizationProfile | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT profile_json FROM profiles WHERE tool_fingerprint=? AND environment=?",
                (fingerprint, environment),
            ).fetchone()
        return OptimizationProfile.model_validate_json(row["profile_json"]) if row else None

    async def retain_telemetry(self, cutoff_iso: str) -> int:
        return await asyncio.to_thread(self._retain_telemetry, cutoff_iso)

    def _retain_telemetry(self, cutoff_iso: str) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM telemetry WHERE timestamp < ?", (cutoff_iso,)
            )
            return cursor.rowcount


def aggregate_outcomes(records: Iterable[TelemetryRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[str(record.outcome)] = counts.get(str(record.outcome), 0) + 1
    return counts
