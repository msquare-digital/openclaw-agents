#!/usr/bin/env python3
"""ACInfinity read-only connector for GrowBox monitoring."""

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

SOURCE = "acinfinity"


def _built_in_mock() -> Dict[str, Any]:
    ts = utc_now_iso()
    return {
        "fetched_at": ts,
        "temperature_c": 24.6,
        "humidity_pct": 62.0,
        "fan_speed_pct": 45.0,
        "raw_ref": "mock:acinfinity:sample",
    }


def _to_metrics(payload: Dict[str, Any], ts: str) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []

    temp = safe_metric(payload.get("temperature_c"))
    humidity = safe_metric(payload.get("humidity_pct"))
    airflow = safe_metric(payload.get("airflow_pct"))
    fan_speed = safe_metric(payload.get("fan_speed_pct"))

    if temp is not None:
        metrics.append({"metric": "air_temp_c", "value": temp, "unit": "C", "timestamp": ts})
    if humidity is not None:
        metrics.append({"metric": "humidity_pct", "value": humidity, "unit": "pct", "timestamp": ts})

    if airflow is not None:
        metrics.append({"metric": "airflow_pct", "value": airflow, "unit": "pct", "timestamp": ts})
    elif fan_speed is not None:
        metrics.append({"metric": "fan_speed_pct", "value": fan_speed, "unit": "pct", "timestamp": ts})

    return metrics


def _fetch_live(timeout: float) -> Dict[str, Any]:
    base_url = os.getenv("ACINFINITY_API_BASE", "").strip()
    if not base_url:
        raise ConnectorError("auth_failed", "missing ACINFINITY_API_BASE", retryable=False)

    token = read_secret_from_env_or_file("ACINFINITY_TOKEN", "ACINFINITY_TOKEN_FILE")
    if not token:
        raise ConnectorError("auth_failed", "missing ACINFINITY_TOKEN or ACINFINITY_TOKEN_FILE", retryable=False)

    device_id = os.getenv("ACINFINITY_DEVICE_ID", "").strip()
    if not device_id:
        raise ConnectorError("schema_changed", "missing ACINFINITY_DEVICE_ID", retryable=False)

    url = f"{base_url.rstrip('/')}/devices/{device_id}/telemetry"
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
        if len(metrics) < 3:
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
