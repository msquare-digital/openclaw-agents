#!/usr/bin/env python3
"""Poll ACInfinity and Ecowitt connectors and emit a combined snapshot."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
CONNECTORS_DIR = ROOT / "connectors"
DEFAULT_THRESHOLDS = ROOT.parent / "config" / "thresholds.example.yaml"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_connector(name: str, timeout: float, mock: bool, mock_file: str) -> Dict[str, Any]:
    script = CONNECTORS_DIR / f"{name}_connector.py"
    cmd = [sys.executable, str(script), "--timeout", str(timeout)]
    if mock:
        cmd.append("--mock")
    if mock_file:
        cmd.extend(["--mock-file", mock_file])

    proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode not in (0, 2):
        return {
            "source": name,
            "status": "error",
            "fetched_at": utc_now_iso(),
            "metrics": [],
            "error": {
                "code": "connector_runtime_error",
                "message": proc.stderr.strip() or "connector failed",
                "retryable": True,
            },
        }

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "source": name,
            "status": "error",
            "fetched_at": utc_now_iso(),
            "metrics": [],
            "error": {
                "code": "schema_changed",
                "message": "connector emitted invalid json",
                "retryable": False,
            },
        }


def build_snapshot(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    devices: List[Dict[str, Any]] = []
    devices_by_source: Dict[str, List[Dict[str, Any]]] = {}
    devices_by_role: Dict[str, List[Dict[str, Any]]] = {}
    missing: List[str] = []
    errors: List[Dict[str, Any]] = []

    required = {
        "acinfinity": ["air_temp_c", "humidity_pct"],
        "ecowitt": ["soil_moisture_pct", "pump_state"],
    }

    for result in results:
        source = result.get("source", "unknown")
        if result.get("status") == "error":
            err = result.get("error", {"code": "unknown", "message": "unknown", "retryable": True})
            errors.append({"source": source, **err})
            missing.extend(required.get(source, []))
            continue

        metric_names = set()
        for item in result.get("metrics", []):
            metric = item.get("metric")
            if metric:
                metrics[metric] = item.get("value")
                metric_names.add(metric)

        for needed in required.get(source, []):
            if needed not in metric_names:
                missing.append(needed)

        for device in result.get("devices", []):
            if isinstance(device, dict):
                devices.append(device)
                devices_by_source.setdefault(source, []).append(device)
                role = str(device.get("role", "unbekannt"))
                devices_by_role.setdefault(role, []).append(device)

    return {
        "snapshot_at": utc_now_iso(),
        "sources": [r.get("source", "unknown") for r in results],
        "metrics": metrics,
        "devices": devices,
        "devices_by_source": devices_by_source,
        "devices_by_role": devices_by_role,
        "missing": sorted(set(missing)),
        "errors": errors,
        "raw": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll growbox data sources")
    parser.add_argument("--mock", action="store_true", help="Run connectors in mock mode")
    parser.add_argument("--timeout", type=float, default=10.0, help="Connector timeout")
    parser.add_argument("--evaluate", action="store_true", help="Evaluate snapshot against thresholds")
    parser.add_argument("--phase", default="veg", help="Grow phase used for evaluation")
    parser.add_argument(
        "--thresholds-file",
        default=str(DEFAULT_THRESHOLDS),
        help="Path to thresholds yaml file",
    )
    parser.add_argument(
        "--source",
        choices=["all", "acinfinity", "ecowitt"],
        default="all",
        help="Poll only one source or all",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    source_names = ["acinfinity", "ecowitt"] if args.source == "all" else [args.source]
    results = [run_connector(name=s, timeout=args.timeout, mock=args.mock, mock_file="") for s in source_names]
    snapshot = build_snapshot(results)
    has_errors = any(r.get("status") == "error" for r in results)

    if args.evaluate:
        from evaluate_snapshot import evaluate_snapshot, load_rules

        rules = load_rules(Path(args.thresholds_file))
        snapshot["evaluation"] = evaluate_snapshot(snapshot=snapshot, rules=rules, phase=args.phase)

    print(json.dumps(snapshot, indent=2, ensure_ascii=False))
    if has_errors:
        sys.exit(2)
    if args.evaluate and snapshot.get("evaluation", {}).get("summary", {}).get("critical", 0) > 0:
        sys.exit(3)
    sys.exit(0)


if __name__ == "__main__":
    main()
