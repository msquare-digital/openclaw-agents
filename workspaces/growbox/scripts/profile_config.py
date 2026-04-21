#!/usr/bin/env python3
"""GrowBox plant profile loader + validator."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent
DEFAULT_PROFILE = ROOT.parent / "config" / "plant-profile.yaml"
DEFAULT_PROFILE_FALLBACK = ROOT.parent / "config" / "plant-profile.example.yaml"
ALLOWED_PHASES = {"seedling", "veg", "bloom"}


def resolve_profile_file() -> Path:
    env = os.getenv("GROWBOX_PLANT_PROFILE_FILE", "").strip()
    if env:
        return Path(env)
    if DEFAULT_PROFILE.exists():
        return DEFAULT_PROFILE
    return DEFAULT_PROFILE_FALLBACK


def _parse_scalar(text: str) -> Any:
    v = text.strip().strip('"').strip("'")
    if v.lower() in {"true", "false"}:
        return v.lower() == "true"
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        return v


def _fallback_parse_yaml(content: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    section = ""
    sublist = ""
    current_plant: Dict[str, Any] | None = None

    for raw in content.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        text = line.strip()

        if indent == 0 and text.endswith(":"):
            section = text[:-1].strip()
            sublist = ""
            current_plant = None
            if section == "plants":
                out.setdefault(section, [])
            else:
                out.setdefault(section, {})
            continue

        if not section:
            continue

        if section == "plants":
            plants = out.setdefault("plants", [])
            if not isinstance(plants, list):
                continue
            if indent == 2 and text.startswith("- "):
                current_plant = {}
                plants.append(current_plant)
                rest = text[2:].strip()
                if rest and ":" in rest:
                    k, v = rest.split(":", 1)
                    current_plant[k.strip()] = _parse_scalar(v)
                continue
            if indent >= 4 and current_plant is not None and ":" in text:
                k, v = text.split(":", 1)
                current_plant[k.strip()] = _parse_scalar(v)
            continue

        node = out.setdefault(section, {})
        if not isinstance(node, dict):
            continue
        if indent == 2 and text.endswith(":"):
            sublist = text[:-1].strip()
            node.setdefault(sublist, [])
            continue
        if indent == 4 and text.startswith("- ") and sublist:
            arr = node.setdefault(sublist, [])
            if isinstance(arr, list):
                arr.append(_parse_scalar(text[2:]))
            continue
        if indent == 2 and ":" in text:
            k, v = text.split(":", 1)
            node[k.strip()] = _parse_scalar(v)
            sublist = ""

    return out


def load_profile(path: Path) -> Dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(content) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return _fallback_parse_yaml(content)


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.strptime(value.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    plant = profile.get("plant", {})
    run = profile.get("run", {})
    setup = profile.get("setup", {})
    plants = profile.get("plants", [])

    if not isinstance(plant, dict):
        errors.append("section 'plant' fehlt oder ist ungueltig")
        plant = {}
    if not isinstance(run, dict):
        errors.append("section 'run' fehlt oder ist ungueltig")
        run = {}
    if not isinstance(setup, dict):
        warnings.append("section 'setup' fehlt oder ist ungueltig")

    phase = str(plant.get("phase", "")).strip().lower()
    if phase and phase not in ALLOWED_PHASES:
        errors.append(f"plant.phase ungueltig: '{phase}' (erlaubt: {sorted(ALLOWED_PHASES)})")
    if not phase:
        warnings.append("plant.phase fehlt")

    phase_current = str(run.get("phase_current", "")).strip().lower()
    if phase_current and phase_current not in ALLOWED_PHASES:
        errors.append(f"run.phase_current ungueltig: '{phase_current}' (erlaubt: {sorted(ALLOWED_PHASES)})")
    if phase and phase_current and phase != phase_current:
        warnings.append(f"plant.phase ({phase}) weicht von run.phase_current ({phase_current}) ab")

    if "germinated_at" in plant and not _is_iso_date(plant.get("germinated_at")):
        errors.append("plant.germinated_at muss YYYY-MM-DD sein")
    if "started_at" in run and not _is_iso_date(run.get("started_at")):
        errors.append("run.started_at muss YYYY-MM-DD sein")

    if not isinstance(plants, list):
        errors.append("section 'plants' muss eine Liste sein")
        plants = []
    if len(plants) == 0:
        warnings.append("plants ist leer")
    else:
        for idx, item in enumerate(plants, start=1):
            if not isinstance(item, dict):
                errors.append(f"plants[{idx}] ist kein Objekt")
                continue
            if not str(item.get("name", "")).strip():
                errors.append(f"plants[{idx}].name fehlt")

    expected_count = run.get("plant_count")
    if expected_count is not None:
        try:
            count = int(expected_count)
            if count != len(plants):
                warnings.append(f"run.plant_count={count} stimmt nicht mit plants={len(plants)} ueberein")
        except (TypeError, ValueError):
            errors.append("run.plant_count muss Zahl sein")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def load_and_validate(path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    profile = load_profile(path)
    report = validate_profile(profile)
    return profile, report

