#!/usr/bin/env python3
"""Reasoned summary/prediction for GrowBox using current + last 24h data."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import urlopen


METRICS_ORDER: List[Tuple[str, str, str]] = [
    ("air_temp_c", "Temp innen", "C"),
    ("humidity_pct", "Feuchte innen", "%"),
    ("vpd_kpa", "VPD innen", "kPa"),
    ("co2_ppm", "CO2", "ppm"),
    ("light_pct", "Licht", "%"),
    ("air_temp_outdoor_c", "Temp aussen", "C"),
    ("humidity_outdoor_pct", "Feuchte aussen", "%"),
    ("vpd_outdoor_kpa", "VPD aussen", "kPa"),
    ("soil_moisture_ch1_pct", "Boden CH1", "%"),
    ("soil_moisture_ch2_pct", "Boden CH2", "%"),
    ("soil_moisture_ch3_pct", "Boden CH3", "%"),
    ("soil_moisture_ch4_pct", "Boden CH4", "%"),
    ("soil_moisture_ch5_pct", "Boden CH5", "%"),
]

DAY_NAMES = {
    0: "Montag",
    1: "Dienstag",
    2: "Mittwoch",
    3: "Donnerstag",
    4: "Freitag",
    5: "Samstag",
    6: "Sonntag",
}


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


def _fmt_num(value: Any, digits: int) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{num:.{digits}f}"


def _metric_digits(metric: str, unit: str) -> int:
    if unit == "%":
        return 0 if metric.startswith("soil_moisture") else 1
    if unit == "ppm":
        return 0
    if unit == "kPa":
        return 2
    return 1


def _parse_hhmm(raw: Any) -> Optional[int]:
    text = str(raw or "").strip()
    if not text:
        return None
    parts = text.split(":", 1)
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


def _lights_expected_on(profile: Dict[str, Any], timezone_name: str) -> Optional[bool]:
    setup = profile.get("setup", {})
    if not isinstance(setup, dict):
        return None
    on_min = _parse_hhmm(setup.get("light_on_hour"))
    off_min = _parse_hhmm(setup.get("light_off_hour"))
    if on_min is None or off_min is None:
        return None

    local = _local_now(timezone_name)
    now_min = local.hour * 60 + local.minute
    if on_min == off_min:
        return True
    if on_min < off_min:
        return on_min <= now_min < off_min
    return now_min >= on_min or now_min < off_min


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _plausible_bounds(metric: str) -> Tuple[float, float]:
    if metric in {"humidity_pct", "humidity_outdoor_pct", "light_pct"}:
        return (0.0, 100.0)
    if metric.startswith("soil_moisture"):
        return (0.0, 100.0)
    if metric in {"co2_ppm"}:
        return (0.0, 5000.0)
    if metric in {"vpd_kpa", "vpd_outdoor_kpa"}:
        return (0.0, 5.0)
    if metric in {"air_temp_c", "air_temp_outdoor_c"}:
        return (-20.0, 60.0)
    return (-1e9, 1e9)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _damped_forecast(last_v: float, delta_window: float, elapsed_h: float, metric: str) -> float:
    # Projection is damped when the observation window is short.
    # With 24h data -> full delta extrapolation; with less -> proportionally reduced.
    coverage = _clamp(elapsed_h / 24.0, 0.0, 1.0)
    projected = last_v + (delta_window * coverage)
    lo, hi = _plausible_bounds(metric)
    return _clamp(projected, lo, hi)


def _classify(value: Optional[float], rule: Dict[str, Any]) -> str:
    if value is None:
        return "sensor_missing"
    cmin = _to_float(rule.get("critical_min"))
    cmax = _to_float(rule.get("critical_max"))
    wmin = _to_float(rule.get("warn_min"))
    wmax = _to_float(rule.get("warn_max"))
    if cmin is not None and value < cmin:
        return "critical"
    if cmax is not None and value > cmax:
        return "critical"
    if wmin is not None and value < wmin:
        return "warn"
    if wmax is not None and value > wmax:
        return "warn"
    return "ok"


def _find_rule(rules: List[Dict[str, Any]], metric: str, phase: str) -> Dict[str, Any]:
    for rule in rules:
        if str(rule.get("metric", "")) == metric and str(rule.get("phase", "")).lower() == phase.lower():
            return rule
    for rule in rules:
        if str(rule.get("metric", "")) == metric and not str(rule.get("phase", "")).strip():
            return rule
    return {}


def _local_now(timezone_name: str) -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(timezone_name))
    except Exception:
        return datetime.now()


def _grow_day_week(profile: Dict[str, Any], now_local: datetime) -> Tuple[Optional[int], Optional[int], str]:
    run = profile.get("run", {}) if isinstance(profile.get("run"), dict) else {}
    plant = profile.get("plant", {}) if isinstance(profile.get("plant"), dict) else {}
    start_raw = str(run.get("started_at") or plant.get("germinated_at") or "").strip()
    if not start_raw:
        return None, None, ""
    try:
        start_date = datetime.fromisoformat(start_raw).date()
        day = (now_local.date() - start_date).days + 1
        if day < 1:
            return None, None, ""
        week = ((day - 1) // 7) + 1
        return day, week, start_raw
    except Exception:
        return None, None, ""


def _series(samples: List[Dict[str, Any]], metric: str) -> List[Tuple[datetime, float]]:
    out: List[Tuple[datetime, float]] = []
    for item in samples:
        metrics = item.get("metrics", {})
        if not isinstance(metrics, dict):
            continue
        val = _to_float(metrics.get(metric))
        if val is None:
            continue
        out.append((_to_dt(str(item.get("snapshot_at", ""))), val))
    return out


def _overall_from_levels(levels: List[str]) -> str:
    if not levels:
        return "sensor_missing"
    if any(l == "critical" for l in levels):
        return "critical"
    if any(l == "warn" for l in levels):
        return "warn"
    if any(l == "sensor_missing" for l in levels):
        return "sensor_missing"
    return "ok"


def _phase_from_profile(profile: Dict[str, Any], fallback: str) -> str:
    run = profile.get("run", {}) if isinstance(profile.get("run"), dict) else {}
    plant = profile.get("plant", {}) if isinstance(profile.get("plant"), dict) else {}
    return str(run.get("phase_current") or plant.get("phase") or fallback or "veg").strip() or "veg"


def _prepare_samples(
    snapshot: Dict[str, Any], samples_24h: List[Dict[str, Any]], active_phase: str
) -> Tuple[List[Dict[str, Any]], str, int]:
    all_samples = list(samples_24h)
    current_snapshot_at = str(snapshot.get("snapshot_at", ""))
    if not any(str(s.get("snapshot_at", "")) == current_snapshot_at for s in all_samples):
        all_samples.append(
            {
                "snapshot_at": current_snapshot_at,
                "phase": active_phase,
                "metrics": snapshot.get("metrics", {}),
                "evaluation": snapshot.get("evaluation", {}),
            }
        )
    all_samples = sorted(all_samples, key=lambda x: str(x.get("snapshot_at", "")))
    current_dt = _to_dt(current_snapshot_at)
    historical_count = sum(1 for s in all_samples if _to_dt(str(s.get("snapshot_at", ""))) < current_dt)
    return all_samples, current_snapshot_at, max(0, historical_count)


def _compute_metric_insights(
    *,
    all_samples: List[Dict[str, Any]],
    rules: List[Dict[str, Any]],
    phase: str,
    profile: Dict[str, Any],
    timezone_name: str,
) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []
    lights_on = _lights_expected_on(profile, timezone_name)
    for metric, label, unit in METRICS_ORDER:
        values = _series(all_samples, metric)
        if not values:
            continue

        first_t, first_v = values[0]
        last_t, last_v = values[-1]
        vals = [v for _, v in values]
        avg_v = mean(vals)
        min_v = min(vals)
        max_v = max(vals)
        delta = last_v - first_v

        elapsed_h = max((last_t - first_t).total_seconds() / 3600.0, 1e-6)
        forecast_12h = _damped_forecast(last_v, delta_window=delta * 0.5, elapsed_h=elapsed_h, metric=metric)
        forecast_24h = _damped_forecast(last_v, delta_window=delta, elapsed_h=elapsed_h, metric=metric)

        rule = _find_rule(rules, metric, phase)
        current_state = _classify(last_v, rule)
        forecast_state = _classify(forecast_24h, rule)
        if metric == "light_pct" and lights_on is False:
            current_state = "ok"
            forecast_state = "ok"

        insights.append(
            {
                "metric": metric,
                "label": label,
                "unit": unit,
                "digits": _metric_digits(metric, unit),
                "current": last_v,
                "min": min_v,
                "max": max_v,
                "avg": avg_v,
                "delta_24h": delta,
                "forecast_12h": forecast_12h,
                "forecast_24h": forecast_24h,
                "current_state": current_state,
                "forecast_state": forecast_state,
            }
        )
    return insights


def _context_header(profile: Dict[str, Any], timezone_name: str, phase: str) -> List[str]:
    now_local = _local_now(timezone_name)
    iso_year, iso_week, iso_day = now_local.isocalendar()
    dow_name = DAY_NAMES.get(iso_day - 1, str(iso_day))
    active_phase = _phase_from_profile(profile, phase)

    run_name = ""
    plant_node = profile.get("plant", {}) if isinstance(profile.get("plant"), dict) else {}
    run_node = profile.get("run", {}) if isinstance(profile.get("run"), dict) else {}
    setup_node = profile.get("setup", {}) if isinstance(profile.get("setup"), dict) else {}
    if isinstance(run_node, dict):
        run_name = str(run_node.get("name", "")).strip()
    if not run_name and isinstance(plant_node, dict):
        run_name = str(plant_node.get("run_name", "")).strip()
    if not run_name and isinstance(setup_node, dict):
        run_name = str(setup_node.get("growbox_name", "")).strip()

    day, grow_week, start_raw = _grow_day_week(profile, now_local)

    lines: List[str] = []
    lines.append(f"- Zeit: {dow_name}, {now_local.strftime('%d.%m.%Y %H:%M')} ({timezone_name})")
    lines.append(f"- Kalender: KW {iso_week}/{iso_year}, Tag {iso_day}")
    if day is not None and grow_week is not None:
        lines.append(f"- Grow-Zyklus: Woche {grow_week}, Tag {day} (Start {start_raw})")
    lines.append(f"- Phase: {active_phase}")
    if run_name:
        lines.append(f"- Run: {run_name}")
    return lines


def fetch_weather_context(profile: Dict[str, Any], timeout: float = 3.0) -> Dict[str, Any]:
    setup = profile.get("setup", {}) if isinstance(profile.get("setup"), dict) else {}
    lat = _to_float(setup.get("latitude"))
    lon = _to_float(setup.get("longitude"))
    if lat is None or lon is None:
        return {"available": False, "reason": "missing setup.latitude/setup.longitude"}

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&forecast_days=2&timezone=auto"
    )
    try:
        with urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError):
        return {"available": False, "reason": "weather request failed"}

    daily = payload.get("daily", {}) if isinstance(payload.get("daily"), dict) else {}
    tmax = daily.get("temperature_2m_max", [])
    tmin = daily.get("temperature_2m_min", [])
    pop = daily.get("precipitation_probability_max", [])
    time_list = daily.get("time", [])

    if not (isinstance(time_list, list) and len(time_list) >= 2):
        return {"available": False, "reason": "weather payload incomplete"}

    def _idx(arr: Any, i: int) -> Optional[float]:
        if not isinstance(arr, list) or len(arr) <= i:
            return None
        return _to_float(arr[i])

    return {
        "available": True,
        "tomorrow": {
            "date": str(time_list[1]),
            "temp_min_c": _idx(tmin, 1),
            "temp_max_c": _idx(tmax, 1),
            "precip_prob_max_pct": _idx(pop, 1),
        },
    }


def build_summary_report(
    *,
    snapshot: Dict[str, Any],
    profile: Dict[str, Any],
    rules: List[Dict[str, Any]],
    samples_24h: List[Dict[str, Any]],
    timezone_name: str,
    phase: str,
) -> str:
    active_phase = _phase_from_profile(profile, phase)
    all_samples, _, historical_count = _prepare_samples(snapshot, samples_24h, active_phase)
    insights = _compute_metric_insights(
        all_samples=all_samples, rules=rules, phase=active_phase, profile=profile, timezone_name=timezone_name
    )

    lines: List[str] = ["GrowBox Summary (24h)"]
    lines.extend(_context_header(profile, timezone_name=timezone_name, phase=active_phase))
    lines.append("")
    lines.append("24h-Zusammenfassung:")

    levels: List[str] = []
    for item in insights:
        levels.append(str(item["current_state"]))
        d = int(item["digits"])
        lines.append(
            "- {label}: Ist {cur}{unit} | min/max {mn}/{mx}{unit} | Mittel {avg}{unit} | Trend24h {delta}{unit} | Zustand {state}.".format(
                label=item["label"],
                cur=_fmt_num(item["current"], d),
                mn=_fmt_num(item["min"], d),
                mx=_fmt_num(item["max"], d),
                avg=_fmt_num(item["avg"], d),
                delta=_fmt_num(item["delta_24h"], d),
                unit=item["unit"],
                state=item["current_state"],
            )
        )

    if not insights:
        lines.append("- Keine verwertbaren Messwerte in den letzten 24h.")

    overall = _overall_from_levels(levels)
    summary_map = {
        "ok": "Ist-Zustand stabil.",
        "warn": "Ist-Zustand mit Warnsignalen.",
        "critical": "Ist-Zustand kritisch.",
        "sensor_missing": "Ist-Zustand unvollstaendig beurteilbar (fehlende Messwerte).",
    }
    lines.append("")
    lines.append("Summary:")
    lines.append(f"- {summary_map.get(overall, summary_map['sensor_missing'])}")
    lines.append(f"- Datenbasis: {historical_count} historische Samples + Live-Snapshot.")
    return "\n".join(lines)


def build_prediction_report(
    *,
    snapshot: Dict[str, Any],
    profile: Dict[str, Any],
    rules: List[Dict[str, Any]],
    samples_24h: List[Dict[str, Any]],
    timezone_name: str,
    phase: str,
    include_weather_context: bool = True,
) -> str:
    active_phase = _phase_from_profile(profile, phase)
    all_samples, _, historical_count = _prepare_samples(snapshot, samples_24h, active_phase)
    insights = _compute_metric_insights(
        all_samples=all_samples, rules=rules, phase=active_phase, profile=profile, timezone_name=timezone_name
    )

    lines: List[str] = ["GrowBox Prediction (Morgen)"]
    lines.extend(_context_header(profile, timezone_name=timezone_name, phase=active_phase))
    lines.append("")
    lines.append("Prognose (aus 24h-Trend):")

    forecast_levels: List[str] = []
    for item in insights:
        forecast_levels.append(str(item["forecast_state"]))
        d = int(item["digits"])
        lines.append(
            "- {label}: erwartet {_24h}{unit} in ~24h | Risiko {risk} (aktuell {cur}{unit}, Trend24h {delta}{unit}).".format(
                label=item["label"],
                _24h=_fmt_num(item["forecast_24h"], d),
                unit=item["unit"],
                risk=item["forecast_state"],
                cur=_fmt_num(item["current"], d),
                delta=_fmt_num(item["delta_24h"], d),
            )
        )

    if not insights:
        lines.append("- Keine verwertbaren Messwerte fuer Prognose vorhanden.")

    overall = _overall_from_levels(forecast_levels)
    prediction_map = {
        "ok": "Morgen voraussichtlich stabil.",
        "warn": "Morgen sind Warn-Abweichungen wahrscheinlich.",
        "critical": "Morgen sind kritische Abweichungen wahrscheinlich.",
        "sensor_missing": "Morgen-Prognose unsicher wegen fehlender Messwerte.",
    }

    if include_weather_context:
        weather = fetch_weather_context(profile)
        lines.append("")
        lines.append("Web-Kontext (Wetter):")
        if weather.get("available"):
            tomorrow = weather.get("tomorrow", {}) if isinstance(weather.get("tomorrow"), dict) else {}
            lines.append(
                "- {date}: aussen min/max {mn}/{mx}C, Regenwahrscheinlichkeit bis {pop}%.".format(
                    date=tomorrow.get("date", "morgen"),
                    mn=_fmt_num(tomorrow.get("temp_min_c"), 1),
                    mx=_fmt_num(tomorrow.get("temp_max_c"), 1),
                    pop=_fmt_num(tomorrow.get("precip_prob_max_pct"), 0),
                )
            )
        else:
            lines.append(f"- Kein Wetter-Kontext verfuegbar ({weather.get('reason', 'unbekannt')}).")

    lines.append("")
    lines.append("Prediction:")
    lines.append(f"- {prediction_map.get(overall, prediction_map['sensor_missing'])}")
    lines.append(f"- Datenbasis: {historical_count} historische Samples + Live-Snapshot.")
    return "\n".join(lines)


def cutoff_24h_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
