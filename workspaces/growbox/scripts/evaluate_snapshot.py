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


def _resolve_thresholds_file() -> Path:
    import os

    env_path = os.getenv("GROWBOX_THRESHOLDS_FILE", "").strip()
    if env_path:
        return Path(env_path)
    primary = Path(__file__).resolve().parent.parent / "config" / "thresholds.yaml"
    if primary.exists():
        return primary
    return Path(__file__).resolve().parent.parent / "config" / "thresholds.example.yaml"


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


def _parse_hhmm(raw: Any) -> Optional[int]:
    text = str(raw or "").strip()
    if not text:
        return None
    m = re.fullmatch(r"(\d{1,2})(?::(\d{1,2}))?", text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


def _load_profile(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    content = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(content) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_profile_file() -> Path:
    import os

    env_path = os.getenv("GROWBOX_PLANT_PROFILE_FILE", "").strip()
    if env_path:
        return Path(env_path)
    primary = Path(__file__).resolve().parent.parent / "config" / "plant-profile.yaml"
    if primary.exists():
        return primary
    return Path(__file__).resolve().parent.parent / "config" / "plant-profile.example.yaml"


def _lights_expected_on(profile: Dict[str, Any], at_iso: str) -> Optional[bool]:
    setup = profile.get("setup", {})
    if not isinstance(setup, dict):
        return None
    on_min = _parse_hhmm(setup.get("light_on_hour"))
    off_min = _parse_hhmm(setup.get("light_off_hour"))
    if on_min is None or off_min is None:
        return None

    tz_name = str(setup.get("timezone", "Europe/Berlin") or "Europe/Berlin")
    text = str(at_iso or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    try:
        from zoneinfo import ZoneInfo

        local = dt.astimezone(ZoneInfo(tz_name))
    except Exception:
        local = dt.astimezone()

    now_min = local.hour * 60 + local.minute
    if on_min == off_min:
        return True
    if on_min < off_min:
        return on_min <= now_min < off_min
    return now_min >= on_min or now_min < off_min


def _recommendation(metric: str, phase: str, severity: str) -> str:
    recs: Dict[str, Dict[str, Dict[str, str]]] = {
        "seedling": {
            "air_temp_c": {
                "warn": "Sanft nachregeln: Heizgeraet/Luefter so anpassen, dass 22-27C stabil erreicht werden.",
                "critical": "Klima sofort stabilisieren; bei >29C Lichtleistung reduzieren, bei <20C waermen.",
            },
            "humidity_pct": {
                "warn": "Luftfeuchte vorsichtig Richtung 60-75% bringen, um Jungpflanzenstress zu vermeiden.",
                "critical": "Sofort gegensteuern: bei zu trocken befeuchten, bei zu feucht entfeuchten/abluften.",
            },
            "soil_moisture_pct": {
                "warn": "Substratfeuchte angleichen; in Coco kleine, haeufige Wassergaben bevorzugen.",
                "critical": "Akut pruefen: Staunaesse oder Austrocknung vermeiden, Drain und Pumpenlauf kontrollieren.",
            },
            "co2_ppm": {
                "warn": "CO2 im moderaten Bereich halten; Frischluft und Umluft fein nachjustieren.",
                "critical": "CO2 sofort pruefen; Sensor plausibilisieren und Frischluftzufuhr sicherstellen.",
            },
            "light_pct": {
                "warn": "Lichtintensitaet fuer Keimlinge sanft anheben/senken, Stressspitzen vermeiden.",
                "critical": "Licht sofort korrigieren, um Verbrennung oder Vergeilung zu verhindern.",
            },
        },
        "veg": {
            "air_temp_c": {
                "warn": "Klima nachregeln, Zielbereich 20-28C stabil halten.",
                "critical": "Sofort gegensteuern; Temperaturabweichung kann Wachstum deutlich bremsen.",
            },
            "humidity_pct": {
                "warn": "Feuchte auf 50-70% einpendeln, VPD im Blick behalten.",
                "critical": "Feuchte sofort korrigieren, Schimmel-/Transpirationsrisiko minimieren.",
            },
            "soil_moisture_pct": {
                "warn": "Bewaesserung feinjustieren; in Coco lieber haeufig und kontrolliert giessen.",
                "critical": "Substratstatus sofort pruefen (zu nass/zu trocken) und Pumpen-/Drainagelauf kontrollieren.",
            },
            "co2_ppm": {
                "warn": "CO2 im Veg-Zielbereich halten; Luftaustausch und Umluft abgleichen.",
                "critical": "CO2-Wert sofort verifizieren und Frischluftzufuhr bzw. Dichtigkeit pruefen.",
            },
            "light_pct": {
                "warn": "Lichtniveau moderat nachregeln, gleichmaessige Canopy-Belichtung sichern.",
                "critical": "Lichtintensitaet sofort anpassen, Hitzestress oder Unterbelichtung vermeiden.",
            },
        },
        "bloom": {
            "air_temp_c": {
                "warn": "Bluete-Klima auf 20-26C nachfuehren, Tag/Nacht-Schwankung begrenzen.",
                "critical": "Sofort stabilisieren; zu hohe Werte schaden Terpenen und Bluetenqualitaet.",
            },
            "humidity_pct": {
                "warn": "RH Richtung 40-55% bringen, Schimmelrisiko in dichten Blueten beachten.",
                "critical": "Akut entfeuchten/abluften; Botrytis-Risiko minimieren.",
            },
            "soil_moisture_pct": {
                "warn": "Giessmenge/Intervall in der Bluete feinjustieren.",
                "critical": "Wurzelzone sofort pruefen; Staunaesse und Trockenstress vermeiden.",
            },
            "co2_ppm": {
                "warn": "CO2 im Bluete-Bereich stabil halten, Luftaustausch abstimmen.",
                "critical": "CO2 sofort verifizieren; Frischluft, Sensorik und Regelung pruefen.",
            },
            "light_pct": {
                "warn": "In der Bluete hohe, aber stabile Intensitaet halten; Hotspots vermeiden.",
                "critical": "Licht sofort korrigieren, um Bleaching oder Ertragsverlust zu vermeiden.",
            },
        },
    }
    phase_rules = recs.get(phase.lower(), {})
    metric_rules = phase_rules.get(metric, {})
    if severity == "sensor_missing":
        return "Sensor/Connector pruefen; ohne Messwert keine sichere Regelentscheidung moeglich."
    if severity in {"warn", "critical"}:
        return metric_rules.get(severity, "")
    return ""


def evaluate_snapshot(
    snapshot: Dict[str, Any], rules: List[Dict[str, Any]], phase: str, profile: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    metrics = snapshot.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    profile = profile if isinstance(profile, dict) else {}
    snapshot_at = str(snapshot.get("snapshot_at", utc_now_iso()))
    lights_on = _lights_expected_on(profile, snapshot_at)

    events: List[Dict[str, Any]] = []

    for rule in rules:
        metric = str(rule.get("metric", "")).strip()
        if not metric:
            continue

        rule_phase = str(rule.get("phase", "")).strip().lower()
        if rule_phase and rule_phase != phase.lower():
            continue

        value = _to_float(metrics.get(metric))
        now = snapshot_at

        if metric == "light_pct" and lights_on is False:
            events.append(
                {
                    "severity": "ok",
                    "metric": metric,
                    "phase": phase,
                    "event_at": now,
                    "current": value,
                    "reason": "lichtfenster aus (light_off_window)",
                    "recommendation": "Keine Alarmierung: Licht ist laut Zeitplan aus.",
                    "thresholds": {
                        "warn_min": _to_float(rule.get("warn_min")),
                        "warn_max": _to_float(rule.get("warn_max")),
                        "critical_min": _to_float(rule.get("critical_min")),
                        "critical_max": _to_float(rule.get("critical_max")),
                        "hysteresis": rule.get("hysteresis"),
                        "cooldown_minutes": rule.get("cooldown_minutes"),
                    },
                }
            )
            continue

        if value is None:
            events.append(
                {
                    "severity": "sensor_missing",
                    "metric": metric,
                    "phase": phase,
                    "event_at": now,
                    "reason": f"metric '{metric}' missing in snapshot",
                    "recommendation": _recommendation(metric=metric, phase=phase, severity="sensor_missing"),
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
                "recommendation": _recommendation(metric=metric, phase=phase, severity=severity),
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
    default_thresholds = _resolve_thresholds_file()
    default_profile = _resolve_profile_file()
    parser = argparse.ArgumentParser(description="Evaluate growbox snapshot")
    parser.add_argument("--snapshot-file", required=True, help="Path to snapshot json")
    parser.add_argument(
        "--thresholds-file",
        default=str(default_thresholds),
        help="Threshold rules file (yaml)",
    )
    parser.add_argument("--phase", default="veg", help="Grow phase")
    parser.add_argument(
        "--plant-profile-file",
        default=str(default_profile),
        help="Plant profile yaml (for schedule-aware metrics like light)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = json.loads(Path(args.snapshot_file).read_text(encoding="utf-8"))
    rules = load_rules(Path(args.thresholds_file))
    profile = _load_profile(Path(args.plant_profile_file))
    result = evaluate_snapshot(snapshot=snapshot, rules=rules, phase=args.phase, profile=profile)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
