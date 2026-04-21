#!/usr/bin/env python3
"""Run one monitoring cycle: poll, evaluate, dedupe, notify via channel command."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from format_telegram_alert import format_telegram_message
from metrics_store import insert_snapshot, prune_older_than_days
from profile_config import load_and_validate, resolve_profile_file
from state_store import load_state, save_state, utc_now_iso

ROOT = Path(__file__).resolve().parent
DEFAULT_STATE_FILE = ROOT.parent / "state" / "monitor_state.json"
DEFAULT_METRICS_DB = ROOT.parent / "state" / "metrics.sqlite3"


def _resolve_thresholds_file() -> Path:
    env_path = os.getenv("GROWBOX_THRESHOLDS_FILE", "").strip()
    if env_path:
        return Path(env_path)
    primary = ROOT.parent / "config" / "thresholds.yaml"
    if primary.exists():
        return primary
    return ROOT.parent / "config" / "thresholds.example.yaml"

def _to_dt(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


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


def _alert_events(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    evaluation = snapshot.get("evaluation", {})
    events = evaluation.get("events", []) if isinstance(evaluation, dict) else []
    if not isinstance(events, list):
        return []
    out: List[Dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        sev = str(event.get("severity", ""))
        if sev in {"warn", "critical"}:
            out.append(event)
    return out


def _severity_rank(sev: str) -> int:
    return {"critical": 2, "warn": 1}.get(str(sev), 0)


def _filter_min_severity(events: List[Dict[str, Any]], min_severity: str) -> List[Dict[str, Any]]:
    target = _severity_rank(min_severity)
    return [e for e in events if _severity_rank(str(e.get("severity", ""))) >= target]


def _event_key(event: Dict[str, Any], phase: str) -> str:
    return f"{phase}:{event.get('metric','?')}:{event.get('severity','?')}"


def _cooldown_minutes(event: Dict[str, Any], default_minutes: int) -> int:
    thresholds = event.get("thresholds", {})
    if not isinstance(thresholds, dict):
        return default_minutes
    try:
        val = int(float(thresholds.get("cooldown_minutes", default_minutes)))
    except (TypeError, ValueError):
        val = default_minutes
    return max(1, val)


def _dedupe_events(
    events: List[Dict[str, Any]], state: Dict[str, Any], phase: str, default_cooldown_minutes: int
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    now = _to_dt(utc_now_iso())
    alerts = state.setdefault("alerts", {})
    send_now: List[Dict[str, Any]] = []
    suppressed: List[Dict[str, Any]] = []

    for event in events:
        key = _event_key(event, phase=phase)
        entry = alerts.get(key, {})
        if not isinstance(entry, dict):
            entry = {}
        last_sent_dt = _to_dt(str(entry.get("last_sent_at", "")))
        cooldown = _cooldown_minutes(event, default_cooldown_minutes)
        seconds_since = (now - last_sent_dt).total_seconds()
        if seconds_since < cooldown * 60:
            suppressed.append(event)
            continue
        send_now.append(event)
    return send_now, suppressed


def _send_notify(command: str, message: str, dry_run: bool) -> None:
    if dry_run or not command.strip():
        print(message)
        return
    proc = subprocess.run(
        command,
        input=message,
        text=True,
        shell=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "notify command failed")


def parse_args() -> argparse.Namespace:
    default_thresholds = _resolve_thresholds_file()
    parser = argparse.ArgumentParser(description="Run one growbox monitoring cycle")
    parser.add_argument("--phase", default="", help="Grow phase (defaults to plant profile phase or veg)")
    parser.add_argument("--thresholds-file", default=str(default_thresholds), help="Threshold yaml file")
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE), help="State json file")
    parser.add_argument("--metrics-db", default=str(DEFAULT_METRICS_DB), help="SQLite file for historical metrics")
    parser.add_argument("--retention-days", type=int, default=30, help="Delete samples older than N days")
    parser.add_argument("--timeout", type=float, default=12.0, help="Connector timeout")
    parser.add_argument("--default-cooldown-minutes", type=int, default=30, help="Fallback cooldown")
    parser.add_argument("--notify-command", default="", help="Shell command to send message via stdin")
    parser.add_argument(
        "--min-severity",
        choices=["warn", "critical"],
        default="warn",
        help="Minimum severity for primary notify channel",
    )
    parser.add_argument(
        "--notify-command-secondary",
        default="",
        help="Optional second shell command to send message via stdin",
    )
    parser.add_argument(
        "--secondary-min-severity",
        choices=["warn", "critical"],
        default="critical",
        help="Minimum severity for secondary notify channel",
    )
    parser.add_argument("--mock", action="store_true", help="Use connector mock mode")
    parser.add_argument("--dry-run", action="store_true", help="Do not send, print only")
    parser.add_argument("--print-json", action="store_true", help="Print result json")
    return parser.parse_args()


def _phase_from_profile() -> str:
    p = resolve_profile_file()
    if not p.exists():
        return "veg"
    try:
        profile, report = load_and_validate(p)
    except Exception as exc:
        print(f"WARN: profile load failed ({p}): {exc}", file=sys.stderr)
        return "veg"
    if report.get("errors"):
        print(f"WARN: profile validation errors: {report['errors']}", file=sys.stderr)

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


def main() -> None:
    args = parse_args()
    phase = args.phase.strip() or _phase_from_profile()
    thresholds_file = Path(args.thresholds_file)
    state_file = Path(args.state_file)
    metrics_db = Path(args.metrics_db)
    notify_command = args.notify_command.strip() or os.getenv("GROWBOX_NOTIFY_COMMAND", "").strip()
    notify_command_secondary = args.notify_command_secondary.strip() or os.getenv(
        "GROWBOX_NOTIFY_COMMAND_SECONDARY", ""
    ).strip()

    state = load_state(state_file)
    snapshot = _run_poll(phase=phase, thresholds_file=thresholds_file, timeout=args.timeout, mock=args.mock)
    insert_snapshot(metrics_db, snapshot=snapshot, phase=phase)
    if args.retention_days > 0:
        prune_older_than_days(metrics_db, args.retention_days)
    events = _alert_events(snapshot)
    send_now, suppressed = _dedupe_events(
        events=events,
        state=state,
        phase=phase,
        default_cooldown_minutes=args.default_cooldown_minutes,
    )

    sent_primary = False
    sent_secondary = False
    if send_now:
        primary_events = _filter_min_severity(send_now, args.min_severity)
        secondary_events = _filter_min_severity(send_now, args.secondary_min_severity)

        # Build temporary snapshot helper with selected events.
        def _format_for(events_subset: List[Dict[str, Any]]) -> str:
            tmp_snapshot = json.loads(json.dumps(snapshot))
            evaluation = tmp_snapshot.get("evaluation", {})
            if isinstance(evaluation, dict):
                evaluation["events"] = events_subset
                evaluation["summary"] = {
                    "ok": 0,
                    "warn": sum(1 for e in events_subset if e.get("severity") == "warn"),
                    "critical": sum(1 for e in events_subset if e.get("severity") == "critical"),
                    "sensor_missing": 0,
                }
            return format_telegram_message(snapshot=tmp_snapshot, phase=phase, max_events=len(events_subset))

        if primary_events:
            message_primary = _format_for(primary_events)
            _send_notify(notify_command, message_primary, dry_run=args.dry_run)
            sent_primary = True

        if notify_command_secondary and secondary_events:
            message_secondary = _format_for(secondary_events)
            _send_notify(notify_command_secondary, message_secondary, dry_run=args.dry_run)
            sent_secondary = True

        # Persist dedupe state for all alert-severity events that passed cooldown.
        # This keeps cooldown logic central regardless of channel fanout.
        for event in send_now:
            key = _event_key(event, phase=phase)
            state.setdefault("alerts", {})[key] = {
                "metric": event.get("metric"),
                "severity": event.get("severity"),
                "phase": phase,
                "last_sent_at": utc_now_iso(),
                "last_value": event.get("current"),
                "last_reason": event.get("reason", ""),
            }

    sent = sent_primary or sent_secondary

    state["last_snapshot_at"] = snapshot.get("snapshot_at", utc_now_iso())
    state["last_status"] = "alert_sent" if sent else ("suppressed" if suppressed else "ok")
    history = state.setdefault("history", [])
    if isinstance(history, list):
        history.append(
            {
                "at": utc_now_iso(),
                "phase": phase,
                    "events_total": len(events),
                    "events_sent": len(send_now),
                    "events_sent_primary": len(_filter_min_severity(send_now, args.min_severity)),
                    "events_sent_secondary": len(_filter_min_severity(send_now, args.secondary_min_severity))
                    if notify_command_secondary
                    else 0,
                    "events_suppressed": len(suppressed),
                    "sent": sent,
                }
        )
        if len(history) > 200:
            state["history"] = history[-200:]

    save_state(state_file, state)

    if args.print_json:
        print(
            json.dumps(
                {
                    "phase": phase,
                    "snapshot_at": snapshot.get("snapshot_at"),
                    "events_total": len(events),
                    "events_sent": len(send_now),
                    "events_sent_primary": len(_filter_min_severity(send_now, args.min_severity)),
                    "events_sent_secondary": len(_filter_min_severity(send_now, args.secondary_min_severity))
                    if notify_command_secondary
                    else 0,
                    "events_suppressed": len(suppressed),
                    "sent": sent,
                    "notify_command": bool(notify_command),
                    "notify_command_secondary": bool(notify_command_secondary),
                },
                indent=2,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
