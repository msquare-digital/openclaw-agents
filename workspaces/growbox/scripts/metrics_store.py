#!/usr/bin/env python3
"""SQLite persistence for growbox snapshots."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(path: Path) -> None:
    with _connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sampled_at TEXT NOT NULL,
                phase TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                evaluation_json TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_sampled_at ON samples(sampled_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_phase ON samples(phase)")


def insert_snapshot(path: Path, snapshot: Dict[str, Any], phase: str) -> None:
    init_db(path)
    sampled_at = str(snapshot.get("snapshot_at") or utc_now_iso())
    metrics = snapshot.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    evaluation = snapshot.get("evaluation")
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT INTO samples(sampled_at, phase, metrics_json, evaluation_json, created_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                sampled_at,
                phase,
                json.dumps(metrics, ensure_ascii=False),
                json.dumps(evaluation, ensure_ascii=False) if evaluation is not None else None,
                utc_now_iso(),
            ),
        )


def read_samples_since(path: Path, since_iso: str, phase: str = "") -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    query = "SELECT sampled_at, phase, metrics_json, evaluation_json FROM samples WHERE sampled_at >= ?"
    params: List[Any] = [since_iso]
    if phase:
        query += " AND phase = ?"
        params.append(phase)
    query += " ORDER BY sampled_at ASC"

    out: List[Dict[str, Any]] = []
    with _connect(path) as conn:
        rows = conn.execute(query, params).fetchall()
    for row in rows:
        metrics: Dict[str, Any] = {}
        evaluation: Any = None
        try:
            metrics = json.loads(str(row["metrics_json"]))
        except Exception:
            metrics = {}
        if row["evaluation_json"]:
            try:
                evaluation = json.loads(str(row["evaluation_json"]))
            except Exception:
                evaluation = None
        out.append(
            {
                "snapshot_at": str(row["sampled_at"]),
                "phase": str(row["phase"]),
                "metrics": metrics if isinstance(metrics, dict) else {},
                "evaluation": evaluation if isinstance(evaluation, dict) else {},
            }
        )
    return out


def prune_older_than_days(path: Path, days: int) -> int:
    if not path.exists():
        return 0
    days = max(1, int(days))
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
    cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    with _connect(path) as conn:
        cur = conn.execute("DELETE FROM samples WHERE sampled_at < ?", (cutoff_dt,))
        return int(cur.rowcount or 0)
