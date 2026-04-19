#!/usr/bin/env python3
"""Ecowitt read-only connector for GrowBox monitoring."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from common import (
    ConnectorError,
    emit,
    http_get_json,
    load_json_file,
    parse_args,
    read_secret_from_env_or_file,
    result_error,
    safe_metric,
    utc_now_iso,
)

SOURCE = "ecowitt"


def _built_in_mock() -> Dict[str, Any]:
    ts = utc_now_iso()
    return {
        "fetched_at": ts,
        "soil_moisture_pct": 34.0,
        "pump_state": "off",
        "raw_ref": "mock:ecowitt:sample",
    }


def _to_metrics(payload: Dict[str, Any], ts: str) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []

    soil = safe_metric(payload.get("soil_moisture_pct"))
    pump_state = str(payload.get("pump_state", "unknown")).lower().strip()

    if soil is not None:
        metrics.append(
            {
                "metric": "soil_moisture_pct",
                "value": soil,
                "unit": "pct",
                "timestamp": ts,
            }
        )

    if pump_state:
        metrics.append(
            {
                "metric": "pump_state",
                "value": pump_state,
                "unit": "state",
                "timestamp": ts,
            }
        )

    return metrics


def _fetch_live(timeout: float) -> Dict[str, Any]:
    base_url = os.getenv("ECOWITT_API_BASE", "").strip()
    if not base_url:
        raise ConnectorError("auth_failed", "missing ECOWITT_API_BASE", retryable=False)

    token = read_secret_from_env_or_file("ECOWITT_TOKEN", "ECOWITT_TOKEN_FILE")
    if not token:
        raise ConnectorError("auth_failed", "missing ECOWITT_TOKEN or ECOWITT_TOKEN_FILE", retryable=False)

    device_id = os.getenv("ECOWITT_DEVICE_ID", "").strip()
    if not device_id:
        raise ConnectorError("schema_changed", "missing ECOWITT_DEVICE_ID", retryable=False)

    url = f"{base_url.rstrip('/')}/devices/{device_id}/status"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    return http_get_json(url, headers=headers, timeout=timeout)


def run() -> Dict[str, Any]:
    args = parse_args(SOURCE)
    ts = utc_now_iso()

    try:
        if args.mock:
            payload = load_json_file(Path(args.mock_file)) if args.mock_file else _built_in_mock()
        else:
            payload = _fetch_live(args.timeout)

        metric_ts = payload.get("fetched_at", ts)
        metrics = _to_metrics(payload, metric_ts)
        if not metrics:
            raise ConnectorError("schema_changed", "no expected metrics in payload", retryable=False)

        status = "ok"
        if len(metrics) < 2:
            status = "degraded"

        result: Dict[str, Any] = {
            "source": SOURCE,
            "status": status,
            "fetched_at": ts,
            "metrics": metrics,
            "raw_ref": payload.get("raw_ref", ""),
        }
        return result
    except ConnectorError as exc:
        return result_error(SOURCE, exc.code, exc.message, exc.retryable)


def main() -> None:
    result = run()
    code = 0 if result["status"] in ("ok", "degraded") else 2
    emit(result, exit_code=code)


if __name__ == "__main__":
    main()
