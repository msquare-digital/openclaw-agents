#!/usr/bin/env python3
"""Generate and optionally push a daily GrowBox summary + prediction report."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from evaluate_snapshot import load_rules
from grow_expert_opinion import generate_expert_opinion
from metrics_store import insert_snapshot, prune_older_than_days, read_samples_since
from profile_config import load_and_validate, resolve_profile_file
from status_reasoning import build_prediction_report, build_summary_report, cutoff_24h_iso

ROOT = Path(__file__).resolve().parent
DEFAULT_METRICS_DB = ROOT.parent / "state" / "metrics.sqlite3"


def _resolve_thresholds_file() -> Path:
    raw = os.getenv("GROWBOX_THRESHOLDS_FILE", "").strip()
    if raw:
        return Path(raw)
    primary = ROOT.parent / "config" / "thresholds.yaml"
    if primary.exists():
        return primary
    return ROOT.parent / "config" / "thresholds.example.yaml"


def _run_poll(phase: str, thresholds_file: Path, timeout: float, mock: bool) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "poll_growbox.py"),
        "--evaluate",
        "--phase",
        phase,
        "--thresholds-file",
        str(thresholds_file),
        "--timeout",
        str(timeout),
    ]
    if mock:
        cmd.append("--mock")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in (0, 2, 3):
        raise RuntimeError(proc.stderr.strip() or "poll_growbox failed")
    return json.loads(proc.stdout)


def _phase_from_profile(profile: Dict[str, Any]) -> str:
    run = profile.get("run", {})
    if isinstance(run, dict):
        phase = str(run.get("phase_current", "")).strip()
        if phase:
            return phase
    plant = profile.get("plant", {})
    if isinstance(plant, dict):
        phase = str(plant.get("phase", "")).strip()
        if phase:
            return phase
    return "veg"


def _send_notify(command: str, message: str, dry_run: bool) -> None:
    if dry_run or not command.strip():
        print(message)
        return
    proc = subprocess.run(command, input=message, text=True, shell=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "notify command failed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate daily growbox summary + prediction report")
    parser.add_argument("--phase", default="", help="Override phase")
    parser.add_argument("--thresholds-file", default=str(_resolve_thresholds_file()), help="Threshold yaml file")
    parser.add_argument("--plant-profile-file", default=str(resolve_profile_file()), help="Plant profile yaml file")
    parser.add_argument("--metrics-db", default=str(DEFAULT_METRICS_DB), help="SQLite metrics db")
    parser.add_argument("--retention-days", type=int, default=60, help="Delete samples older than N days")
    parser.add_argument("--timeout", type=float, default=12.0, help="Connector timeout")
    parser.add_argument("--notify-command", default="", help="Shell command to send message via stdin")
    parser.add_argument("--notify-command-secondary", default="", help="Optional second shell command")
    parser.add_argument("--with-opinion", action="store_true", help="Add LLM expert opinion block")
    parser.add_argument("--mock", action="store_true", help="Use mock connector mode")
    parser.add_argument("--dry-run", action="store_true", help="Do not send, print only")
    parser.add_argument("--print-json", action="store_true", help="Print machine result json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    profile_file = Path(args.plant_profile_file)
    thresholds_file = Path(args.thresholds_file)
    metrics_db = Path(args.metrics_db)

    profile, report = load_and_validate(profile_file)
    if report.get("errors"):
        raise RuntimeError("plant profile invalid: " + "; ".join(str(x) for x in report["errors"]))

    phase = args.phase.strip() or _phase_from_profile(profile)
    rules: List[Dict[str, Any]] = load_rules(thresholds_file)

    snapshot = _run_poll(phase=phase, thresholds_file=thresholds_file, timeout=args.timeout, mock=args.mock)
    insert_snapshot(metrics_db, snapshot=snapshot, phase=phase)
    if args.retention_days > 0:
        prune_older_than_days(metrics_db, args.retention_days)

    setup = profile.get("setup", {}) if isinstance(profile.get("setup"), dict) else {}
    timezone_name = str(setup.get("timezone", "Europe/Berlin") or "Europe/Berlin")

    samples = read_samples_since(metrics_db, since_iso=cutoff_24h_iso(), phase=phase)
    summary_text = build_summary_report(
        snapshot=snapshot,
        profile=profile,
        rules=rules,
        samples_24h=samples,
        timezone_name=timezone_name,
        phase=phase,
    )
    prediction_text = build_prediction_report(
        snapshot=snapshot,
        profile=profile,
        rules=rules,
        samples_24h=samples,
        timezone_name=timezone_name,
        phase=phase,
        include_weather_context=True,
    )
    blocks = [summary_text, prediction_text]
    if args.with_opinion:
        opinion = generate_expert_opinion(
            snapshot=snapshot,
            profile=profile,
            phase=phase,
            samples_24h=samples,
            summary_text=summary_text,
            prediction_text=prediction_text,
        )
        blocks.append("GrowBox Expert Opinion\n" + opinion)
    message = "\n\n---\n\n".join(blocks)

    notify_command = args.notify_command.strip() or os.getenv("GROWBOX_NOTIFY_COMMAND", "").strip()
    notify_command_secondary = args.notify_command_secondary.strip() or os.getenv(
        "GROWBOX_NOTIFY_COMMAND_SECONDARY", ""
    ).strip()
    _send_notify(notify_command, message, dry_run=args.dry_run)
    if notify_command_secondary:
        _send_notify(notify_command_secondary, message, dry_run=args.dry_run)

    if args.print_json:
        print(
            json.dumps(
                {
                    "phase": phase,
                    "snapshot_at": snapshot.get("snapshot_at"),
                    "samples_24h": len(samples),
                    "notify_command": bool(notify_command),
                    "notify_command_secondary": bool(notify_command_secondary),
                },
                indent=2,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
