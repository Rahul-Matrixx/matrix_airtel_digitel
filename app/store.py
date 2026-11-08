"""Tiny JSON store for the demo: consent ledger, audit log, orders, clusters.

Production swaps this for an encrypted database; the interface stays the same.
Only masked identifiers are ever written here.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone

from .config import STATE_DIR

_LOCK = threading.Lock()


def _path(name: str):
    return STATE_DIR / f"{name}.json"


def _load(name: str) -> dict:
    p = _path(name)
    return json.loads(p.read_text()) if p.exists() else {}


def _save(name: str, data: dict) -> None:
    _path(name).write_text(json.dumps(data, indent=1, default=str))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def put(table: str, key: str, value: dict) -> dict:
    with _LOCK:
        data = _load(table)
        data[key] = value
        _save(table, data)
    return value


def get(table: str, key: str) -> dict | None:
    return _load(table).get(key)


def all_rows(table: str) -> dict:
    return _load(table)


def audit(event: str, **fields) -> None:
    """Append-only audit trail. Callers pass masked identifiers only."""
    with _LOCK:
        data = _load("audit")
        data[str(len(data) + 1)] = {"at": now(), "event": event, **fields}
        _save("audit", data)
