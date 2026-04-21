#!/usr/bin/env python3
"""State persistence helpers for GrowBox monitoring."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "updated_at": utc_now_iso(),
        "last_snapshot_at": "",
        "last_status": "unknown",
        "alerts": {},
        "history": [],
    }


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_state()
    if not isinstance(data, dict):
        return default_state()
    merged = default_state()
    merged.update(data)
    if not isinstance(merged.get("alerts"), dict):
        merged["alerts"] = {}
    if not isinstance(merged.get("history"), list):
        merged["history"] = []
    return merged


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now_iso()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)

