#!/usr/bin/env python3
"""Expert grow opinion via OpenClaw agent (uses configured primary model)."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compact_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
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
    ]
    return {k: metrics.get(k) for k in keys if k in metrics}


def _series_stats(samples_24h: List[Dict[str, Any]], metric: str) -> Dict[str, Any]:
    values: List[float] = []
    first: Optional[float] = None
    last: Optional[float] = None
    for item in samples_24h:
        metrics = item.get("metrics", {})
        if not isinstance(metrics, dict):
            continue
        v = _to_float(metrics.get(metric))
        if v is None:
            continue
        if first is None:
            first = v
        last = v
        values.append(v)

    if not values:
        return {"samples": 0}

    return {
        "samples": len(values),
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / max(1, len(values)),
        "delta": (last - first) if first is not None and last is not None else 0.0,
        "last": last,
    }


def _build_context(
    *,
    snapshot: Dict[str, Any],
    profile: Dict[str, Any],
    phase: str,
    samples_24h: List[Dict[str, Any]],
    summary_text: str,
    prediction_text: str,
) -> Dict[str, Any]:
    metrics = snapshot.get("metrics", {}) if isinstance(snapshot.get("metrics"), dict) else {}
    setup = profile.get("setup", {}) if isinstance(profile.get("setup"), dict) else {}
    cultivation = profile.get("cultivation", {}) if isinstance(profile.get("cultivation"), dict) else {}
    nutrients = profile.get("nutrients", {}) if isinstance(profile.get("nutrients"), dict) else {}
    plants = profile.get("plants", []) if isinstance(profile.get("plants"), list) else []

    stats = {
        "air_temp_c": _series_stats(samples_24h, "air_temp_c"),
        "humidity_pct": _series_stats(samples_24h, "humidity_pct"),
        "vpd_kpa": _series_stats(samples_24h, "vpd_kpa"),
        "co2_ppm": _series_stats(samples_24h, "co2_ppm"),
        "light_pct": _series_stats(samples_24h, "light_pct"),
        "soil_ch1": _series_stats(samples_24h, "soil_moisture_ch1_pct"),
        "soil_ch2": _series_stats(samples_24h, "soil_moisture_ch2_pct"),
        "soil_ch3": _series_stats(samples_24h, "soil_moisture_ch3_pct"),
        "soil_ch4": _series_stats(samples_24h, "soil_moisture_ch4_pct"),
        "soil_ch5": _series_stats(samples_24h, "soil_moisture_ch5_pct"),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "phase": phase,
        "snapshot_at": snapshot.get("snapshot_at"),
        "current_metrics": _compact_metrics(metrics),
        "profile": {
            "plant": profile.get("plant", {}),
            "run": profile.get("run", {}),
            "setup": setup,
            "cultivation": cultivation,
            "nutrients": nutrients,
            "plants": plants,
        },
        "stats_24h": stats,
        "summary_text": summary_text,
        "prediction_text": prediction_text,
    }


def _looks_like_prompt_echo(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    markers = [
        "Rolle: Indoor-Grow-Berater",
        "Kontext JSON:",
        "\"generated_at\":",
        "Erstelle eine Experteneinschaetzung",
    ]
    return any(m in t for m in markers)


def _collect_candidates(node: Any) -> List[Tuple[int, str]]:
    candidates: List[Tuple[int, str]] = []

    def add(score: int, value: Any) -> None:
        if isinstance(value, str):
            t = value.strip()
            if t:
                candidates.append((score, t))

    def walk(x: Any, score: int) -> None:
        if isinstance(x, dict):
            # Strong preference: explicit assistant-style fields.
            role = str(x.get("role", "")).lower()
            if role == "assistant":
                add(score + 200, x.get("content"))
                add(score + 200, x.get("text"))

            for key in ("response", "final", "reply", "assistant_response", "assistant", "output_text"):
                if key in x:
                    walk(x.get(key), score + 120)
            for key in ("text", "content"):
                if key in x:
                    walk(x.get(key), score + 60)
            for key in ("message", "output", "result", "data"):
                if key in x:
                    walk(x.get(key), score + 40)

            for _, v in x.items():
                walk(v, score)
            return

        if isinstance(x, list):
            for item in x:
                walk(item, score)
            return

        if isinstance(x, str):
            add(score, x)

    walk(node, 0)
    return candidates


def _extract_text_recursive(node: Any) -> str:
    candidates = _collect_candidates(node)
    if not candidates:
        return ""

    # 1) Prefer non-echo texts by score then length.
    filtered = [(s, t) for s, t in candidates if not _looks_like_prompt_echo(t)]
    if filtered:
        filtered.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
        return filtered[0][1]

    # 2) Fallback: best scored text, even if echo.
    candidates.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
    return candidates[0][1]


def generate_expert_opinion(
    *,
    snapshot: Dict[str, Any],
    profile: Dict[str, Any],
    phase: str,
    samples_24h: List[Dict[str, Any]],
    summary_text: str,
    prediction_text: str,
    timeout: float = 90.0,
) -> str:
    agent_id = os.getenv("GROWBOX_OPINION_AGENT_ID", "growbox").strip() or "growbox"
    thinking = os.getenv("GROWBOX_OPINION_THINKING", "medium").strip() or "medium"
    context = _build_context(
        snapshot=snapshot,
        profile=profile,
        phase=phase,
        samples_24h=samples_24h,
        summary_text=summary_text,
        prediction_text=prediction_text,
    )

    prompt = (
        "Rolle: Indoor-Grow-Berater mit Schwerpunkt Coco-Coir und Autoflower.\n"
        "Regeln: nutze nur den Kontext, keine Halluzinationen, Deutsch, knapp und operativ.\n\n"
        "Erstelle eine Experteneinschaetzung fuer die naechsten 24h basierend auf diesem Kontext.\n"
        "Format:\n"
        "1) Einordnung (2-3 Saetze)\n"
        "2) Top 3 Risiken (kurz)\n"
        "3) Konkrete Aktionen fuer heute (max 5 Bulletpoints)\n"
        "4) Was ich morgen wahrscheinlich sehe (1-2 Saetze)\n\n"
        f"Kontext JSON:\n{json.dumps(context, ensure_ascii=False)}"
    )

    cmd = [
        "openclaw",
        "agent",
        "--agent",
        agent_id,
        "--message",
        prompt,
        "--thinking",
        thinking,
        "--json",
        "--timeout",
        str(int(timeout)),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except Exception as exc:
        return f"Expert Opinion nicht verfuegbar: OpenClaw CLI Fehler ({exc})."
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        if len(detail) > 300:
            detail = detail[:300] + "..."
        return f"Expert Opinion nicht verfuegbar: openclaw agent Fehler ({detail})."

    try:
        body = json.loads(proc.stdout)
    except Exception:
        text = (proc.stdout or "").strip()
        if not text:
            return "Expert Opinion nicht verfuegbar: keine JSON-Antwort vom openclaw agent."
        return text

    text = _extract_text_recursive(body)
    if not text:
        compact = json.dumps(body, ensure_ascii=False)
        if len(compact) > 400:
            compact = compact[:400] + "..."
        return f"Expert Opinion nicht verfuegbar: leere Agent-Antwort. raw={compact}"
    return text
