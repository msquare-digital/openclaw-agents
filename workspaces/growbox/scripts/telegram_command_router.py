#!/usr/bin/env python3
"""Handle Telegram pull/config commands for GrowBox."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from format_telegram_alert import format_telegram_message
from grow_expert_opinion import generate_expert_opinion
from metrics_store import insert_snapshot, read_samples_since
from profile_config import load_and_validate, load_profile, resolve_profile_file
from status_reasoning import build_prediction_report, build_summary_report, cutoff_24h_iso
from state_store import load_state

ROOT = Path(__file__).resolve().parent
DEFAULT_STATE_FILE = ROOT.parent / "state" / "monitor_state.json"
DEFAULT_METRICS_DB = ROOT.parent / "state" / "metrics.sqlite3"


def _resolve_profile_file_from_env_or_default() -> Path:
    raw = os.getenv("GROWBOX_PLANT_PROFILE_FILE", "").strip()
    if raw:
        return Path(raw)
    return resolve_profile_file()


def _resolve_thresholds_file() -> Path:
    raw = os.getenv("GROWBOX_THRESHOLDS_FILE", "").strip()
    if raw:
        return Path(raw)
    primary = ROOT.parent / "config" / "thresholds.yaml"
    if primary.exists():
        return primary
    return ROOT.parent / "config" / "thresholds.example.yaml"


def _parse_scalar(value: str) -> Any:
    v = value.strip().strip('"').strip("'")
    if v.lower() in {"true", "false"}:
        return v.lower() == "true"
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        return v


def _load_yaml(path: Path) -> Dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(content) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        parsed = load_profile(path)
        if not isinstance(parsed, dict):
            parsed = {}
        parsed["__raw_text"] = content
        return parsed


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return f'"{str(value)}"'


def _update_raw_profile_text(raw_text: str, section: str, key: str, value: Any) -> str:
    lines = raw_text.splitlines()
    section_header = f"{section}:"
    start = -1
    for i, line in enumerate(lines):
        if line.strip() == section_header and not line.startswith(" "):
            start = i
            break
    if start < 0:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(section_header)
        lines.append(f"  {key}: {_yaml_scalar(value)}")
        return "\n".join(lines).rstrip() + "\n"

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].strip() and not lines[i].startswith(" "):
            end = i
            break

    pattern = re.compile(rf"^\s{{2}}{re.escape(key)}\s*:")
    replaced = False
    for i in range(start + 1, end):
        if pattern.match(lines[i]):
            lines[i] = f"  {key}: {_yaml_scalar(value)}"
            replaced = True
            break

    if not replaced:
        insert_at = end
        while insert_at > start + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, f"  {key}: {_yaml_scalar(value)}")

    return "\n".join(lines).rstrip() + "\n"


def _dump_profile_yaml(data: Dict[str, Any]) -> str:
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError("PyYAML fehlt: /profil set erfordert python3-yaml") from exc

    # Keep explicit section order for readability.
    ordered: Dict[str, Any] = {}
    for sec in ("plant", "setup", "cultivation", "nutrients", "run", "plants"):
        if sec in data:
            ordered[sec] = data[sec]
    for k, v in data.items():
        if k not in ordered and not str(k).startswith("__"):
            ordered[k] = v
    dumped = yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False)
    return dumped if dumped.endswith("\n") else dumped + "\n"


def _load_threshold_rules(path: Path) -> List[Dict[str, Any]]:
    from evaluate_snapshot import load_rules

    return load_rules(path)


def _dump_thresholds_yaml(rules: List[Dict[str, Any]]) -> str:
    order = [
        "metric",
        "phase",
        "warn_min",
        "warn_max",
        "critical_min",
        "critical_max",
        "cooldown_minutes",
        "hysteresis",
    ]
    lines = ["rules:"]
    for rule in rules:
        lines.append("  - metric: " + str(rule.get("metric", "")))
        for key in order[1:]:
            if key not in rule:
                continue
            lines.append(f"    {key}: {rule.get(key)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _run_poll(phase: str, thresholds_file: Path) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "poll_growbox.py"),
        "--evaluate",
        "--phase",
        phase,
        "--thresholds-file",
        str(thresholds_file),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in (0, 2, 3):
        raise RuntimeError(proc.stderr.strip() or "poll failed")
    return json.loads(proc.stdout)


def _get_phase(profile: Dict[str, Any], fallback: str) -> str:
    raw = profile.get("__raw_text")
    if isinstance(raw, str) and raw.strip():
        match = re.search(r"^\s*phase_current:\s*['\"]?([^'\"\n#]+)", raw, flags=re.MULTILINE)
        if match:
            return match.group(1).strip()
        match = re.search(r"^\s*phase:\s*['\"]?([^'\"\n#]+)", raw, flags=re.MULTILINE)
        if match:
            return match.group(1).strip()

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
    return fallback


def _status_text(
    snapshot: Dict[str, Any],
    phase: str,
) -> str:
    return format_telegram_message(snapshot=snapshot, phase=phase, max_events=5)


def _werte_text(snapshot: Dict[str, Any]) -> str:
    metrics = snapshot.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    lines = ["Werte:"]
    for key in (
        "air_temp_c",
        "humidity_pct",
        "vpd_kpa",
        "co2_ppm",
        "light_pct",
        "air_temp_outdoor_c",
        "humidity_outdoor_pct",
        "vpd_outdoor_kpa",
        "soil_moisture_ch1_pct",
        "soil_moisture_ch2_pct",
        "soil_moisture_ch3_pct",
        "soil_moisture_ch4_pct",
        "soil_moisture_ch5_pct",
        "pump_state",
        "pump_power_w",
    ):
        if key in metrics:
            lines.append(f"- {key}: {metrics[key]}")
    return "\n".join(lines)


def _alarme_text(state_file: Path) -> str:
    state = load_state(state_file)
    alerts = state.get("alerts", {})
    if not isinstance(alerts, dict) or not alerts:
        return "Alarme: keine gespeicherten Alert-Events."
    lines = ["Alarme (letzte bekannte Events):"]
    for key, val in sorted(alerts.items()):
        if not isinstance(val, dict):
            continue
        lines.append(
            f"- {key} | value={val.get('last_value')} | at={val.get('last_sent_at')} | reason={val.get('last_reason')}"
        )
    return "\n".join(lines)


def _hilfe_text() -> str:
    return "\n".join(
        [
            "Verfuegbare Befehle:",
            "- /growstatus",
            "- /summary",
            "- /prediction",
            "- /opinion",
            "- /werte",
            "- /alarme",
            "- /hilfe",
            "- /phase <seedling|veg|bloom>",
            "- /profil show",
            "- /profil validate",
            "- /profil set <plant.*|setup.*|run.*|cultivation.*|nutrients.*> <wert>",
            "- /threshold show [metric]",
            "- /threshold set <metric> <warn_min|warn_max|critical_min|critical_max|cooldown_minutes|hysteresis> <wert> [phase]",
        ]
    )


def _set_profile_value(profile: Dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    if len(parts) != 2:
        raise ValueError("profile key must be section.key")
    section, key = parts
    if section not in {"plant", "setup", "run", "cultivation", "nutrients"}:
        raise ValueError("profile section must be one of: plant, setup, run, cultivation, nutrients")
    if "__raw_text" in profile:
        profile["__raw_text"] = _update_raw_profile_text(str(profile["__raw_text"]), section=section, key=key, value=value)
        return
    node = profile.setdefault(section, {})
    if not isinstance(node, dict):
        node = {}
        profile[section] = node
    node[key] = value


def _threshold_show(rules: List[Dict[str, Any]], metric: str) -> str:
    out = [r for r in rules if str(r.get("metric", "")) == metric] if metric else rules
    if not out:
        return "Keine passenden Threshold-Regeln gefunden."
    return json.dumps(out, indent=2, ensure_ascii=False)


def _threshold_set(rules: List[Dict[str, Any]], metric: str, field: str, value: Any, phase: str) -> List[Dict[str, Any]]:
    target = None
    for rule in rules:
        if str(rule.get("metric", "")) == metric and str(rule.get("phase", "")) == phase:
            target = rule
            break
    if target is None:
        target = {"metric": metric, "phase": phase}
        rules.append(target)
    target[field] = value
    return rules


def parse_args() -> argparse.Namespace:
    default_profile = str(_resolve_profile_file_from_env_or_default())
    default_thresholds = str(_resolve_thresholds_file())
    parser = argparse.ArgumentParser(description="Handle one Telegram command for GrowBox")
    parser.add_argument("--command", required=True, help="Incoming Telegram command text")
    parser.add_argument("--phase", default="", help="Override phase")
    parser.add_argument("--plant-profile-file", default=default_profile)
    parser.add_argument("--thresholds-file", default=default_thresholds)
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--metrics-db", default=str(DEFAULT_METRICS_DB))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    command = args.command.strip()
    tokens = shlex.split(command)
    if not tokens:
        print(_hilfe_text())
        return

    profile_file = Path(args.plant_profile_file)
    thresholds_file = Path(args.thresholds_file)
    state_file = Path(args.state_file)
    metrics_db = Path(args.metrics_db)
    profile = _load_yaml(profile_file)
    phase = args.phase.strip() or _get_phase(profile, "veg")
    rules = _load_threshold_rules(thresholds_file)

    head = tokens[0].lower()

    if head == "/hilfe":
        print(_hilfe_text())
        return

    if head == "/phase":
        if len(tokens) < 2:
            print(f"Aktuelle Phase: {phase}")
            return
        new_phase = tokens[1].strip().lower()
        try:
            _set_profile_value(profile, "plant.phase", new_phase)
            _set_profile_value(profile, "run.phase_current", new_phase)
            if "__raw_text" in profile:
                profile_file.write_text(str(profile["__raw_text"]), encoding="utf-8")
            else:
                profile_file.write_text(_dump_profile_yaml(profile), encoding="utf-8")
        except Exception as exc:
            print(f"Fehler: {exc}")
            return
        _, report = load_and_validate(profile_file)
        print(f"Phase gesetzt: {new_phase}")
        if report.get("warnings"):
            print("Hinweis: " + "; ".join(str(w) for w in report["warnings"]))
        return

    if head == "/profil":
        if len(tokens) >= 2 and tokens[1].lower() == "validate":
            _, report = load_and_validate(profile_file)
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return
        if len(tokens) >= 2 and tokens[1].lower() == "show":
            if "__raw_text" in profile:
                print(profile["__raw_text"])
                return
            print(json.dumps(profile, indent=2, ensure_ascii=False))
            return
        if len(tokens) >= 4 and tokens[1].lower() == "set":
            key = tokens[2]
            value = _parse_scalar(" ".join(tokens[3:]))
            try:
                _set_profile_value(profile, key, value)
                if "__raw_text" in profile:
                    profile_file.write_text(str(profile["__raw_text"]), encoding="utf-8")
                else:
                    profile_file.write_text(_dump_profile_yaml(profile), encoding="utf-8")
            except Exception as exc:
                print(f"Fehler: {exc}")
                return
            _, report = load_and_validate(profile_file)
            print(f"Profil aktualisiert: {key}={value}")
            if report.get("warnings"):
                print("Hinweis: " + "; ".join(str(w) for w in report["warnings"]))
            return
        print("Usage: /profil show | /profil set <section.key> <value>")
        return

    if head == "/threshold":
        if len(tokens) >= 2 and tokens[1].lower() == "show":
            metric = tokens[2] if len(tokens) >= 3 else ""
            print(_threshold_show(rules, metric))
            return
        if len(tokens) >= 5 and tokens[1].lower() == "set":
            metric = tokens[2]
            field = tokens[3]
            value = _parse_scalar(tokens[4])
            target_phase = tokens[5] if len(tokens) >= 6 else phase
            rules = _threshold_set(rules, metric=metric, field=field, value=value, phase=target_phase)
            thresholds_file.write_text(_dump_thresholds_yaml(rules), encoding="utf-8")
            print(f"Threshold aktualisiert: {metric}.{field}={value} (phase={target_phase})")
            return
        print(
            "Usage: /threshold show [metric] | /threshold set <metric> <field> <value> [phase]"
        )
        return

    if head in {"/growstatus", "/summary", "/prediction", "/opinion", "/werte"}:
        snapshot = _run_poll(phase=phase, thresholds_file=thresholds_file)
        insert_snapshot(metrics_db, snapshot=snapshot, phase=phase)
        if head == "/growstatus":
            print(_status_text(snapshot=snapshot, phase=phase))
        elif head == "/summary":
            tz = "Europe/Berlin"
            setup = profile.get("setup", {})
            if isinstance(setup, dict):
                tz = str(setup.get("timezone", tz) or tz)
            samples = read_samples_since(metrics_db, since_iso=cutoff_24h_iso(), phase=phase)
            print(
                build_summary_report(
                    snapshot=snapshot,
                    profile=profile,
                    rules=rules,
                    samples_24h=samples,
                    timezone_name=tz,
                    phase=phase,
                )
            )
        elif head == "/prediction":
            tz = "Europe/Berlin"
            setup = profile.get("setup", {})
            if isinstance(setup, dict):
                tz = str(setup.get("timezone", tz) or tz)
            samples = read_samples_since(metrics_db, since_iso=cutoff_24h_iso(), phase=phase)
            print(
                build_prediction_report(
                    snapshot=snapshot,
                    profile=profile,
                    rules=rules,
                    samples_24h=samples,
                    timezone_name=tz,
                    phase=phase,
                    include_weather_context=True,
                )
            )
        elif head == "/opinion":
            samples = read_samples_since(metrics_db, since_iso=cutoff_24h_iso(), phase=phase)
            tz = "Europe/Berlin"
            setup = profile.get("setup", {})
            if isinstance(setup, dict):
                tz = str(setup.get("timezone", tz) or tz)
            summary_text = build_summary_report(
                snapshot=snapshot,
                profile=profile,
                rules=rules,
                samples_24h=samples,
                timezone_name=tz,
                phase=phase,
            )
            prediction_text = build_prediction_report(
                snapshot=snapshot,
                profile=profile,
                rules=rules,
                samples_24h=samples,
                timezone_name=tz,
                phase=phase,
                include_weather_context=True,
            )
            print(
                "GrowBox Expert Opinion\n"
                + generate_expert_opinion(
                    snapshot=snapshot,
                    profile=profile,
                    phase=phase,
                    samples_24h=samples,
                    summary_text=summary_text,
                    prediction_text=prediction_text,
                )
            )
        else:
            print(_werte_text(snapshot=snapshot))
        return

    if head == "/alarme":
        print(_alarme_text(state_file=state_file))
        return

    print(_hilfe_text())


if __name__ == "__main__":
    main()
