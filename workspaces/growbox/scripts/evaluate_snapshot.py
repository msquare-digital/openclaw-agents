#!/usr/bin/env python3
"""Evaluate growbox snapshots against threshold rules."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_scalar(value: str) -> Any:
    text = value.strip().strip('"').strip("'")
    if text == "":
        return ""
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    if re.fullmatch(r"-?\d+", text):
        try:
            return int(text)
        except ValueError:
            return text
    if re.fullmatch(r"-?\d+\.\d+", text):
        try:
            return float(text)
        except ValueError:
            return text
    return text


def _parse_simple_yaml_rules(content: str) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for raw_line in content.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        stripped = line.strip()
        if stripped == "rules:":
            continue

        if stripped.startswith("- "):
            if current:
                rules.append(current)
            current = {}
            item = stripped[2:].strip()
            if item and ":" in item:
                key, val = item.split(":", 1)
                current[key.strip()] = _parse_scalar(val)
            continue

        if current is None:
            continue

        if ":" in stripped:
            key, val = stripped.split(":", 1)
            current[key.strip()] = _parse_scalar(val)

    if current:
        rules.append(current)

    return rules


def load_rules(path: Path) -> List[Dict[str, Any]]:
    content = path.read_text(encoding="utf-8")

    try:
        import yaml  # type: ignore

        data = yaml.safe_load(content) or {}
        rules = data.get("rules", [])
        if not isinstance(rules, list):
            raise ValueError("rules must be a list")
        return [r for r in rules if isinstance(r, dict)]
    except Exception:
        return _parse_simple_yaml_rules(content)


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_snapshot(snapshot: Dict[str, Any], rules: List[Dict[str, Any]], phase: str) -> Dict[str, Any]:
    metrics = snapshot.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}

    events: List[Dict[str, Any]] = []

    for rule in rules:
        metric = str(rule.get("metric", "")).strip()
        if not metric:
            continue

        rule_phase = str(rule.get("phase", "")).strip().lower()
        if rule_phase and rule_phase != phase.lower():
            continue

        value = _to_float(metrics.get(metric))
        now = snapshot.get("snapshot_at", utc_now_iso())

        if value is None:
            events.append(
                {
                    "severity": "sensor_missing",
                    "metric": metric,
                    "phase": phase,
                    "event_at": now,
                    "reason": f"metric '{metric}' missing in snapshot",
                    "rule": rule,
                }
            )
            continue

        warn_min = _to_float(rule.get("warn_min"))
        warn_max = _to_float(rule.get("warn_max"))
        critical_min = _to_float(rule.get("critical_min"))
        critical_max = _to_float(rule.get("critical_max"))

        severity = "ok"
        reason = "within target range"

        if critical_min is not None and value < critical_min:
            severity = "critical"
            reason = f"{value} < critical_min {critical_min}"
        elif critical_max is not None and value > critical_max:
            severity = "critical"
            reason = f"{value} > critical_max {critical_max}"
        elif warn_min is not None and value < warn_min:
            severity = "warn"
            reason = f"{value} < warn_min {warn_min}"
        elif warn_max is not None and value > warn_max:
            severity = "warn"
            reason = f"{value} > warn_max {warn_max}"

        events.append(
            {
                "severity": severity,
                "metric": metric,
                "phase": phase,
                "event_at": now,
                "current": value,
                "reason": reason,
                "thresholds": {
                    "warn_min": warn_min,
                    "warn_max": warn_max,
                    "critical_min": critical_min,
                    "critical_max": critical_max,
                    "hysteresis": rule.get("hysteresis"),
                    "cooldown_minutes": rule.get("cooldown_minutes"),
                },
            }
        )

    summary = {
        "ok": sum(1 for e in events if e["severity"] == "ok"),
        "warn": sum(1 for e in events if e["severity"] == "warn"),
        "critical": sum(1 for e in events if e["severity"] == "critical"),
        "sensor_missing": sum(1 for e in events if e["severity"] == "sensor_missing"),
    }

    return {
        "phase": phase,
        "evaluated_at": utc_now_iso(),
        "summary": summary,
        "events": events,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate growbox snapshot")
    parser.add_argument("--snapshot-file", required=True, help="Path to snapshot json")
    parser.add_argument(
        "--thresholds-file",
        default=str(Path(__file__).resolve().parent.parent / "config" / "thresholds.example.yaml"),
        help="Threshold rules file (yaml)",
    )
    parser.add_argument("--phase", default="veg", help="Grow phase")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = json.loads(Path(args.snapshot_file).read_text(encoding="utf-8"))
    rules = load_rules(Path(args.thresholds_file))
    result = evaluate_snapshot(snapshot=snapshot, rules=rules, phase=args.phase)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
