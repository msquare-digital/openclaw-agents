#!/usr/bin/env python3
"""Ecowitt cloud read-only connector for GrowBox monitoring."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

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
    now_epoch = str(int(datetime.now(timezone.utc).timestamp()))
    return {
        "code": 0,
        "msg": "success",
        "time": now_epoch,
        "data": {
            "soil_ch1": {
                "soilmoisture": {"time": now_epoch, "unit": "%", "value": "49"}
            },
            "AC1100-EXAMPLE": {
                "status": {"value": 0, "unit": "", "time": now_epoch},
                "power": {"value": "0", "unit": "W", "time": now_epoch},
            },
        },
        "_raw_ref": "mock:ecowitt:cloud",
    }


def _epoch_to_iso(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return utc_now_iso()
    try:
        ts = int(float(text))
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError):
        return utc_now_iso()


def _extract_soil(
    data: Dict[str, Any], selected_channel: int, ts: str
) -> Tuple[List[Dict[str, Any]], bool, List[Dict[str, Any]]]:
    metrics: List[Dict[str, Any]] = []
    devices: List[Dict[str, Any]] = []
    selected_found = False

    for key, node in data.items():
        if not key.startswith("soil_ch"):
            continue
        channel_str = key.replace("soil_ch", "")
        if not channel_str.isdigit() or not isinstance(node, dict):
            continue

        reading = node.get("soilmoisture", {})
        if not isinstance(reading, dict):
            continue

        soil_value = safe_metric(reading.get("value"))
        if soil_value is None:
            continue

        channel = int(channel_str)
        reading_ts = _epoch_to_iso(reading.get("time")) if reading.get("time") else ts

        metrics.append(
            {
                "metric": f"soil_moisture_ch{channel}_pct",
                "value": soil_value,
                "unit": "pct",
                "timestamp": reading_ts,
            }
        )
        devices.append(
            {
                "device_id": key,
                "device_name": f"Soil Sensor CH{channel}",
                "source": SOURCE,
                "role": "bodenfeuchte",
                "metrics": {"soil_moisture_pct": soil_value},
                "timestamp": reading_ts,
            }
        )

        if channel == selected_channel:
            selected_found = True
            metrics.append(
                {
                    "metric": "soil_moisture_pct",
                    "value": soil_value,
                    "unit": "pct",
                    "timestamp": reading_ts,
                }
            )

    return metrics, selected_found, devices


def _extract_pump_state(
    data: Dict[str, Any], plug_key: str, ts: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    metrics: List[Dict[str, Any]] = []
    devices: List[Dict[str, Any]] = []

    candidates: List[Tuple[str, Dict[str, Any]]] = []
    if plug_key and isinstance(data.get(plug_key), dict):
        candidates.append((plug_key, data[plug_key]))
    else:
        for key in sorted(data.keys()):
            node = data.get(key)
            if not isinstance(node, dict):
                continue
            if isinstance(node.get("status"), dict):
                candidates.append((key, node))

    selected_key = plug_key if plug_key else (candidates[0][0] if candidates else "")

    for key, node in candidates:
        status_node = node.get("status", {})
        if not isinstance(status_node, dict):
            continue

        status_raw = safe_metric(status_node.get("value"))
        if status_raw is None:
            continue

        state = "on" if int(status_raw) == 1 else "off"
        status_ts = _epoch_to_iso(status_node.get("time")) if status_node.get("time") else ts

        device_metrics: Dict[str, Any] = {"pump_state": state}
        if key == selected_key:
            metrics.append(
                {
                    "metric": "pump_state",
                    "value": state,
                    "unit": "state",
                    "timestamp": status_ts,
                }
            )
            metrics.append(
                {
                    "metric": "pump_device_key",
                    "value": key,
                    "unit": "id",
                    "timestamp": status_ts,
                }
            )

        power_node = node.get("power", {})
        if isinstance(power_node, dict):
            power_value = safe_metric(power_node.get("value"))
            if power_value is not None:
                power_ts = _epoch_to_iso(power_node.get("time")) if power_node.get("time") else status_ts
                device_metrics["pump_power_w"] = power_value
                if key == selected_key:
                    metrics.append(
                        {
                            "metric": "pump_power_w",
                            "value": power_value,
                            "unit": "W",
                            "timestamp": power_ts,
                        }
                    )

        devices.append(
            {
                "device_id": key,
                "device_name": f"Pump Plug {key}",
                "source": SOURCE,
                "metrics": device_metrics,
                "timestamp": status_ts,
            }
        )

    return metrics, devices


def _to_metrics(payload: Dict[str, Any], ts: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    data = payload.get("data", {})
    if not isinstance(data, dict):
        raise ConnectorError("schema_changed", "ecowitt response has no object data", retryable=False)

    try:
        selected_channel = int(os.getenv("ECOWITT_SOIL_CHANNEL", "1").strip() or "1")
    except ValueError:
        selected_channel = 1

    plug_key = os.getenv("ECOWITT_PLUG_DEVICE_KEY", "").strip()

    soil_metrics, selected_found, soil_devices = _extract_soil(data, selected_channel, ts)
    if soil_metrics and not selected_found:
        # Fallback to first soil channel as canonical soil_moisture_pct
        first_soil = next((m for m in soil_metrics if m["metric"].startswith("soil_moisture_ch")), None)
        if first_soil:
            soil_metrics.append(
                {
                    "metric": "soil_moisture_pct",
                    "value": first_soil["value"],
                    "unit": "pct",
                    "timestamp": first_soil["timestamp"],
                }
            )

    pump_metrics, pump_devices = _extract_pump_state(data, plug_key=plug_key, ts=ts)
    for dev in pump_devices:
        dev["role"] = "pumpe"

    try:
        expected_soil_channels = int(os.getenv("ECOWITT_EXPECT_SOIL_CHANNELS", "5").strip() or "5")
    except ValueError:
        expected_soil_channels = 5
    existing_soil_ids = {str(dev.get("device_id", "")) for dev in soil_devices}
    for channel in range(1, max(1, expected_soil_channels) + 1):
        dev_id = f"soil_ch{channel}"
        if dev_id in existing_soil_ids:
            continue
        soil_devices.append(
            {
                "device_id": dev_id,
                "device_name": f"Soil Sensor CH{channel}",
                "source": SOURCE,
                "role": "bodenfeuchte",
                "metrics": {},
                "timestamp": ts,
                "status": "missing",
            }
        )

    return soil_metrics + pump_metrics, soil_devices + pump_devices


def _fetch_live(timeout: float) -> Dict[str, Any]:
    base_url = os.getenv("ECOWITT_API_BASE", "https://api.ecowitt.net/api/v3").strip()

    application_key = read_secret_from_env_or_file(
        "ECOWITT_APPLICATION_KEY",
        "ECOWITT_APPLICATION_KEY_FILE",
        pass_env_key="ECOWITT_APPLICATION_KEY_PASS_ENTRY",
        default_pass_entry="growbox/ecowitt/application_key",
    )
    if not application_key:
        raise ConnectorError("auth_failed", "missing ECOWITT application_key", retryable=False)

    api_key = read_secret_from_env_or_file(
        "ECOWITT_API_KEY",
        "ECOWITT_API_KEY_FILE",
        pass_env_key="ECOWITT_API_KEY_PASS_ENTRY",
        default_pass_entry="growbox/ecowitt/api_key",
    )
    if not api_key:
        raise ConnectorError("auth_failed", "missing ECOWITT api_key", retryable=False)

    mac = read_secret_from_env_or_file(
        "ECOWITT_MAC",
        "ECOWITT_MAC_FILE",
        pass_env_key="ECOWITT_MAC_PASS_ENTRY",
        default_pass_entry="growbox/ecowitt/mac",
    )
    if not mac:
        # compatibility fallback
        mac = os.getenv("ECOWITT_DEVICE_ID", "").strip()
    if not mac:
        raise ConnectorError("schema_changed", "missing ECOWITT mac", retryable=False)

    callback = os.getenv("ECOWITT_CALLBACK", "all").strip() or "all"

    query = urlencode(
        {
            "application_key": application_key,
            "api_key": api_key,
            "mac": mac,
            "call_back": callback,
        }
    )
    endpoint = f"{base_url.rstrip('/')}/device/real_time?{query}"
    payload = http_get_json(endpoint, headers={"Accept": "application/json"}, timeout=timeout)

    if str(payload.get("code", "")) != "0":
        msg = str(payload.get("msg", "unknown ecowitt error"))
        raise ConnectorError("auth_failed", msg, retryable=False)

    payload["_raw_ref"] = f"ecowitt:mac:{mac}"
    return payload


def run() -> Dict[str, Any]:
    args = parse_args(SOURCE)
    ts = utc_now_iso()

    try:
        if args.mock:
            payload = load_json_file(Path(args.mock_file)) if args.mock_file else _built_in_mock()
        else:
            payload = _fetch_live(args.timeout)

        payload_ts = _epoch_to_iso(payload.get("time")) if payload.get("time") else ts
        metrics, device_entries = _to_metrics(payload, payload_ts)
        if not metrics:
            raise ConnectorError("schema_changed", "no expected metrics in ecowitt payload", retryable=False)

        names = {m.get("metric") for m in metrics}
        status = "ok" if {"soil_moisture_pct", "pump_state"}.issubset(names) else "degraded"

        result: Dict[str, Any] = {
            "source": SOURCE,
            "status": status,
            "fetched_at": ts,
            "metrics": metrics,
            "devices": device_entries,
            "raw_ref": payload.get("_raw_ref", ""),
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
