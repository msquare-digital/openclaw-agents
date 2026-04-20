#!/usr/bin/env python3
"""Format a growbox snapshot as a Telegram alert message."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SEVERITY_ICON = {
    "critical": "🔴",
    "warn": "🟠",
    "ok": "🟢",
    "sensor_missing": "⚪",
}


def _fmt_num(value: Any, digits: int = 1) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return "-"
    if digits <= 0:
        return str(int(round(f)))
    return f"{f:.{digits}f}"


def _fmt_value(metric: str, value: Any) -> str:
    if value is None:
        return "-"
    if metric in {"air_temp_c", "air_temp_outdoor_c"}:
        return f"{_fmt_num(value, 1)}°C"
    if metric in {"humidity_pct", "humidity_outdoor_pct", "light_pct"}:
        return f"{_fmt_num(value, 1)}%"
    if metric in {"vpd_kpa", "vpd_outdoor_kpa"}:
        return f"{_fmt_num(value, 2)} kPa"
    if metric == "co2_ppm":
        return f"{_fmt_num(value, 0)} ppm"
    if metric.startswith("soil_moisture"):
        return f"{_fmt_num(value, 0)}%"
    if metric == "pump_power_w":
        return f"{_fmt_num(value, 1)} W"
    return str(value)


def _extract_soils(metrics: Dict[str, Any]) -> List[Tuple[str, str]]:
    items: List[Tuple[str, str]] = []
    for channel in range(1, 6):
        key = f"soil_moisture_ch{channel}_pct"
        if key in metrics:
            items.append((f"CH{channel}", _fmt_value(key, metrics.get(key))))
    return items


def _severity_rank(sev: str) -> int:
    return {"critical": 0, "warn": 1, "sensor_missing": 2, "ok": 3}.get(sev, 9)


def _top_events(snapshot: Dict[str, Any], max_events: int) -> List[Dict[str, Any]]:
    evaluation = snapshot.get("evaluation", {})
    events = evaluation.get("events", []) if isinstance(evaluation, dict) else []
    if not isinstance(events, list):
        return []
    typed = [e for e in events if isinstance(e, dict)]
    typed.sort(key=lambda e: (_severity_rank(str(e.get("severity", ""))), str(e.get("metric", ""))))
    return typed[:max_events]


def _overall_status(snapshot: Dict[str, Any]) -> str:
    evaluation = snapshot.get("evaluation", {})
    summary = evaluation.get("summary", {}) if isinstance(evaluation, dict) else {}
    critical = int(summary.get("critical", 0) or 0)
    warn = int(summary.get("warn", 0) or 0)
    missing = int(summary.get("sensor_missing", 0) or 0)
    if critical > 0:
        return "critical"
    if warn > 0:
        return "warn"
    if missing > 0:
        return "sensor_missing"
    return "ok"


def format_telegram_message(snapshot: Dict[str, Any], phase: str, max_events: int) -> str:
    metrics = snapshot.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}

    sev = _overall_status(snapshot)
    icon = SEVERITY_ICON.get(sev, "⚪")
    header = f"{icon} GrowBox {phase.upper()} | {str(sev).upper()}"

    lines: List[str] = [header]
    lines.append("")
    lines.append("Innen:")
    lines.append(
        "  Temp {t} | Feuchte {h} | VPD {v} | CO2 {c} | Licht {l}".format(
            t=_fmt_value("air_temp_c", metrics.get("air_temp_c")),
            h=_fmt_value("humidity_pct", metrics.get("humidity_pct")),
            v=_fmt_value("vpd_kpa", metrics.get("vpd_kpa")),
            c=_fmt_value("co2_ppm", metrics.get("co2_ppm")),
            l=_fmt_value("light_pct", metrics.get("light_pct")),
        )
    )

    lines.append("Aussen:")
    lines.append(
        "  Temp {t} | Feuchte {h} | VPD {v}".format(
            t=_fmt_value("air_temp_outdoor_c", metrics.get("air_temp_outdoor_c")),
            h=_fmt_value("humidity_outdoor_pct", metrics.get("humidity_outdoor_pct")),
            v=_fmt_value("vpd_outdoor_kpa", metrics.get("vpd_outdoor_kpa")),
        )
    )

    soils = _extract_soils(metrics)
    if soils:
        soil_text = " | ".join([f"{name} {value}" for name, value in soils])
    else:
        soil_text = _fmt_value("soil_moisture_pct", metrics.get("soil_moisture_pct"))
    lines.append("Boden:")
    lines.append(f"  {soil_text}")

    lines.append("Pumpe:")
    lines.append(
        "  Status {state} | Leistung {power}".format(
            state=str(metrics.get("pump_state", "-")),
            power=_fmt_value("pump_power_w", metrics.get("pump_power_w")),
        )
    )

    top = _top_events(snapshot, max_events=max_events)
    if top:
        lines.append("")
        lines.append("Events:")
        for event in top:
            ev_sev = str(event.get("severity", "sensor_missing"))
            ev_icon = SEVERITY_ICON.get(ev_sev, "⚪")
            metric = str(event.get("metric", "?"))
            current = event.get("current")
            reason = str(event.get("reason", "")).strip()
            if current is None:
                lines.append(f"  {ev_icon} {metric}: {reason}")
            else:
                lines.append(f"  {ev_icon} {metric}: {_fmt_value(metric, current)} ({reason})")

    return "\n".join(lines).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Format snapshot as Telegram message")
    parser.add_argument("--snapshot-file", help="Path to snapshot json, else stdin")
    parser.add_argument("--phase", default="veg", help="Grow phase label for header")
    parser.add_argument("--max-events", type=int, default=6, help="Max events to include")
    return parser.parse_args()


def _load_snapshot(path: Optional[str]) -> Dict[str, Any]:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    raw = sys.stdin.read()
    return json.loads(raw)


def main() -> None:
    args = parse_args()
    snapshot = _load_snapshot(args.snapshot_file)
    text = format_telegram_message(snapshot=snapshot, phase=args.phase, max_events=args.max_events)
    print(text)


if __name__ == "__main__":
    main()
