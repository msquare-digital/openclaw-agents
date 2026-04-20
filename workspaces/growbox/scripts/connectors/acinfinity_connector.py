#!/usr/bin/env python3
"""ACInfinity cloud read-only connector for GrowBox monitoring."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from common import (
    ConnectorError,
    emit,
    http_post_form_json,
    load_json_file,
    parse_args,
    read_secret_from_env_or_file,
    result_error,
    safe_metric,
    utc_now_iso,
)

SOURCE = "acinfinity"
EXPECTED_ROLES = ("heizung", "befeuchter", "abluft", "lampe", "sensoren")
SENSOR_TYPE_META: Dict[int, Tuple[str, str]] = {
    1: ("temperature_c", "C"),
    2: ("humidity_pct", "pct"),
    3: ("vpd_kpa", "kPa"),
    5: ("temperature_c", "C"),
    6: ("humidity_pct", "pct"),
    7: ("vpd_kpa", "kPa"),
    # Common in ACInfinity ecosystems; kept as best-effort labels.
    8: ("co2_ppm", "ppm"),
    9: ("light_lux", "lux"),
    # Observed on BioStation X payloads.
    11: ("co2_ppm", "ppm"),
    12: ("light_pct", "pct"),
}


def _built_in_mock() -> Dict[str, Any]:
    return {
        "code": 200,
        "msg": "success.",
        "data": [
            {
                "devId": "mock-controller-1",
                "deviceInfo": {
                    "temperature": 2466,
                    "humidity": 6210,
                    "speak": 5,
                },
            }
        ],
        "_raw_ref": "mock:acinfinity:devInfoListAll",
    }


def _iter_key_values(obj: Any, parent_key: str = "") -> Iterable[Tuple[str, Any]]:
    if isinstance(obj, dict):
        for key, val in obj.items():
            compound = f"{parent_key}.{key}" if parent_key else key
            yield key, val
            yield from _iter_key_values(val, compound)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            compound = f"{parent_key}[{idx}]" if parent_key else f"[{idx}]"
            yield from _iter_key_values(item, compound)


def _normalize_temperature(val: Any) -> Optional[float]:
    num = safe_metric(val)
    if num is None:
        return None
    # ACInfinity payload commonly uses x100 for temperature.
    if abs(num) > 150:
        num = num / 100.0
    return num


def _normalize_humidity(val: Any) -> Optional[float]:
    num = safe_metric(val)
    if num is None:
        return None
    # ACInfinity payload commonly uses x100 for humidity.
    if abs(num) > 100:
        num = num / 100.0
    return num


def _normalize_speed_to_pct(val: Any) -> Optional[float]:
    num = safe_metric(val)
    if num is None:
        return None
    # Common scale is 0..10.
    if 0 <= num <= 10:
        return num * 10.0
    if 0 <= num <= 100:
        return num
    return None


def _get_device_candidates(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        # Some implementations may wrap list in keys.
        for key in ("list", "devices", "devInfoList"):
            nested = data.get(key)
            if isinstance(nested, list):
                return [d for d in nested if isinstance(d, dict)]
        return [data]
    return []


def _pick_device(devices: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not devices:
        return None

    wanted = os.getenv("ACINFINITY_DEVICE_ID", "").strip()
    if not wanted:
        return devices[0]

    for device in devices:
        for key in ("devId", "deviceId", "id"):
            if str(device.get(key, "")).strip() == wanted:
                return device
        info = device.get("deviceInfo", {})
        if isinstance(info, dict):
            for key in ("devId", "deviceId", "id"):
                if str(info.get(key, "")).strip() == wanted:
                    return device
    return devices[0]


def _parse_role_overrides() -> Dict[str, str]:
    """Parse ACINFINITY_ROLE_MAP=id1:role,id2:role,..."""
    raw = os.getenv("ACINFINITY_ROLE_MAP", "").strip()
    mapping: Dict[str, str] = {}
    if not raw:
        return mapping

    for pair in raw.split(","):
        token = pair.strip()
        if not token or ":" not in token:
            continue
        dev_id, role = token.split(":", 1)
        dev_id = dev_id.strip()
        role = role.strip().lower()
        if dev_id and role:
            mapping[dev_id] = role
    return mapping


def _device_id(device: Dict[str, Any]) -> str:
    for key in ("devId", "deviceId", "id"):
        ident = device.get(key)
        if ident:
            return str(ident)
    if isinstance(device.get("deviceInfo"), dict):
        for key in ("devId", "deviceId", "id"):
            ident = device["deviceInfo"].get(key)
            if ident:
                return str(ident)
    return "unknown"


def _device_name(device: Dict[str, Any], fallback: str) -> str:
    return str(
        device.get("name")
        or device.get("devName")
        or device.get("deviceName")
        or (device.get("deviceInfo", {}) if isinstance(device.get("deviceInfo"), dict) else {}).get("name")
        or fallback
    )


def _classify_role(device: Dict[str, Any], device_id: str, role_overrides: Dict[str, str]) -> str:
    if device_id in role_overrides:
        return role_overrides[device_id]

    parts: List[str] = []
    for key, val in _iter_key_values(device):
        key_l = str(key).lower()
        if key_l in {
            "name",
            "devname",
            "devicename",
            "type",
            "devtype",
            "model",
            "modename",
            "nickname",
            "productname",
            "category",
            "producttype",
        }:
            parts.append(str(val).lower())

    text = " ".join(parts)
    if any(k in text for k in ("heater", "heat", "heizung", "thermo", "warm")):
        return "heizung"
    if any(k in text for k in ("humid", "befeucht", "befeuchter", "nebler", "mist")):
        return "befeuchter"
    if any(k in text for k in ("fan", "abluft", "umluft", "inline", "exhaust", "vent")):
        return "abluft"
    if any(k in text for k in ("light", "lampe", "led", "grow light")):
        return "lampe"
    if any(k in text for k in ("sensor", "probe", "hygro", "thermo", "vpd")):
        return "sensoren"
    return "unbekannt"


def _extract_device_metrics(device: Dict[str, Any], ts: str) -> Tuple[Dict[str, Any], str]:
    temp_val: Optional[float] = None
    humidity_val: Optional[float] = None
    speed_pct_val: Optional[float] = None

    for key, val in _iter_key_values(device):
        k = key.lower()
        if temp_val is None and k in {"temperature", "temperature_c", "temp"}:
            temp_val = _normalize_temperature(val)
        if humidity_val is None and k in {"humidity", "humidity_pct", "humi"}:
            humidity_val = _normalize_humidity(val)
        if speed_pct_val is None and k in {"speak", "onspead", "onselfspead", "fanspeed", "fan_speed"}:
            speed_pct_val = _normalize_speed_to_pct(val)

    device_id = _device_id(device)

    mapped: Dict[str, Any] = {}
    if temp_val is not None:
        mapped["air_temp_c"] = temp_val
    if humidity_val is not None:
        mapped["humidity_pct"] = humidity_val
    if speed_pct_val is not None:
        mapped["fan_speed_pct"] = speed_pct_val

    return mapped, device_id


def _infer_port_role(port_name: str) -> str:
    text = (port_name or "").strip().lower()
    if any(k in text for k in ("heiz", "heater", "heat", "warm")):
        return "heizung"
    if any(k in text for k in ("befeucht", "humid", "mist", "nebler")):
        return "befeuchter"
    if any(k in text for k in ("abluft", "umluft", "fan", "exhaust", "vent", "luefter", "lüfter")):
        return "abluft"
    if any(k in text for k in ("lampe", "light", "led")):
        return "lampe"
    return "unbekannt"


def _state_from_int(value: Any) -> str:
    num = safe_metric(value)
    if num is None:
        return "unknown"
    return "on" if int(num) == 1 else "off"


def _normalize_sensor_value(sensor_type: int, raw: Any) -> Optional[float]:
    if sensor_type in {1, 5}:
        return _normalize_temperature(raw)
    if sensor_type in {2, 6}:
        return _normalize_humidity(raw)

    num = safe_metric(raw)
    if num is None:
        return None
    if sensor_type in {3, 7} and abs(num) > 20:
        return num / 100.0
    if sensor_type in {12} and abs(num) > 100:
        # 1000 -> 100.0% in app UI.
        return num / 10.0
    return num


def _sensor_metric_meta(sensor_type: int) -> Tuple[str, str]:
    return SENSOR_TYPE_META.get(sensor_type, (f"sensor_type_{sensor_type}", "raw"))


def _extract_component_entries(
    device: Dict[str, Any], ts: str, role_overrides: Dict[str, str]
) -> Tuple[List[Dict[str, Any]], Set[str]]:
    entries: List[Dict[str, Any]] = []
    seen_roles: Set[str] = set()

    controller_metrics, controller_id = _extract_device_metrics(device, ts)
    controller_name = _device_name(device, "controller")

    if controller_metrics:
        controller_role = role_overrides.get(controller_id, "sensoren")
        entries.append(
            {
                "device_id": controller_id,
                "device_name": controller_name,
                "source": SOURCE,
                "role": controller_role,
                "metrics": controller_metrics,
                "timestamp": ts,
            }
        )
        if controller_role in EXPECTED_ROLES:
            seen_roles.add(controller_role)

    info = device.get("deviceInfo", {})
    if not isinstance(info, dict):
        return entries, seen_roles

    ports = info.get("ports")
    if isinstance(ports, list):
        for port in ports:
            if not isinstance(port, dict):
                continue
            port_no = int(safe_metric(port.get("port")) or 0)
            if port_no <= 0:
                continue

            port_name = str(port.get("portName") or f"Port {port_no}")
            port_id = f"{controller_id}:port:{port_no}"
            role = role_overrides.get(port_id, _infer_port_role(port_name))
            metrics: Dict[str, Any] = {
                "port_number": port_no,
                "port_state": _state_from_int(port.get("loadState")),
                "port_online": int(safe_metric(port.get("online")) or 0),
            }
            speed = _normalize_speed_to_pct(port.get("speak"))
            if speed is not None:
                metrics["fan_speed_pct"] = speed

            if role == "unbekannt":
                continue
            seen_roles.add(role)
            entries.append(
                {
                    "device_id": port_id,
                    "device_name": port_name,
                    "source": SOURCE,
                    "role": role,
                    "metrics": metrics,
                    "timestamp": ts,
                }
            )

    sensors = info.get("sensors")
    if isinstance(sensors, list):
        for sensor in sensors:
            if not isinstance(sensor, dict):
                continue
            sensor_type = int(safe_metric(sensor.get("sensorType")) or 0)
            sensor_key = str(sensor.get("sensorKey") or f"type{sensor_type}")
            sensor_id = f"{controller_id}:sensor:{sensor_key}"
            role = role_overrides.get(sensor_id, "sensoren")
            value = _normalize_sensor_value(sensor_type, sensor.get("sensorData"))
            metric_key, metric_unit = _sensor_metric_meta(sensor_type)
            metrics = {
                "sensor_type": sensor_type,
                "access_port": int(safe_metric(sensor.get("accessPort")) or 0),
                "sensor_metric": metric_key,
                "sensor_unit": metric_unit,
            }
            if value is not None:
                metrics[metric_key] = value
            entries.append(
                {
                    "device_id": sensor_id,
                    "device_name": f"Sensor {sensor_key} ({metric_key})",
                    "source": SOURCE,
                    "role": role,
                    "metrics": metrics,
                    "timestamp": ts,
                }
            )
            if role in EXPECTED_ROLES:
                seen_roles.add(role)

    return entries, seen_roles


def _sensor_metrics_by_port(device: Dict[str, Any]) -> Dict[int, Dict[str, float]]:
    info = device.get("deviceInfo", {})
    if not isinstance(info, dict):
        return {}
    sensors = info.get("sensors")
    if not isinstance(sensors, list):
        return {}

    by_port: Dict[int, Dict[str, float]] = {}
    for sensor in sensors:
        if not isinstance(sensor, dict):
            continue
        sensor_type = int(safe_metric(sensor.get("sensorType")) or 0)
        port = int(safe_metric(sensor.get("accessPort")) or 0)
        if sensor_type <= 0 or port <= 0:
            continue
        value = _normalize_sensor_value(sensor_type, sensor.get("sensorData"))
        if value is None:
            continue
        metric_key, _unit = _sensor_metric_meta(sensor_type)
        by_port.setdefault(port, {})[metric_key] = value
    return by_port


def _select_canonical_metrics(device: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
    metrics = dict(base)
    by_port = _sensor_metrics_by_port(device)
    if not by_port:
        return metrics

    try:
        indoor_port = int(os.getenv("ACINFINITY_INDOOR_PORT", "1").strip() or "1")
    except ValueError:
        indoor_port = 1
    try:
        outdoor_port = int(os.getenv("ACINFINITY_OUTDOOR_PORT", "7").strip() or "7")
    except ValueError:
        outdoor_port = 7

    indoor = by_port.get(indoor_port, {})
    outdoor = by_port.get(outdoor_port, {})

    if "temperature_c" in indoor:
        metrics["air_temp_c"] = indoor["temperature_c"]
    if "humidity_pct" in indoor:
        metrics["humidity_pct"] = indoor["humidity_pct"]
    if "vpd_kpa" in indoor:
        metrics["vpd_kpa"] = indoor["vpd_kpa"]

    if "temperature_c" in outdoor:
        metrics["air_temp_outdoor_c"] = outdoor["temperature_c"]
    if "humidity_pct" in outdoor:
        metrics["humidity_outdoor_pct"] = outdoor["humidity_pct"]
    if "vpd_kpa" in outdoor:
        metrics["vpd_outdoor_kpa"] = outdoor["vpd_kpa"]

    # CO2/light can be on a dedicated sensor port; expose first seen values.
    for port_data in by_port.values():
        if "co2_ppm" in port_data and "co2_ppm" not in metrics:
            metrics["co2_ppm"] = port_data["co2_ppm"]
        if "light_pct" in port_data and "light_pct" not in metrics:
            metrics["light_pct"] = port_data["light_pct"]

    return metrics


def _resolve_auth(timeout: float, base_url: str) -> Tuple[str, str]:
    token = read_secret_from_env_or_file(
        "ACINFINITY_TOKEN",
        "ACINFINITY_TOKEN_FILE",
        pass_env_key="ACINFINITY_TOKEN_PASS_ENTRY",
        default_pass_entry="growbox/acinfinity/token",
    )
    user_id = os.getenv("ACINFINITY_USER_ID", "").strip()

    if token:
        return token, user_id or token

    email = read_secret_from_env_or_file(
        "ACINFINITY_EMAIL",
        "ACINFINITY_EMAIL_FILE",
        pass_env_key="ACINFINITY_EMAIL_PASS_ENTRY",
        default_pass_entry="growbox/acinfinity/email",
    )
    password = read_secret_from_env_or_file(
        "ACINFINITY_PASSWORD",
        "ACINFINITY_PASSWORD_FILE",
        pass_env_key="ACINFINITY_PASSWORD_PASS_ENTRY",
        default_pass_entry="growbox/acinfinity/password",
    )

    if not email or not password:
        raise ConnectorError(
            "auth_failed",
            "missing ACINFINITY auth: set token or email/password",
            retryable=False,
        )

    # API limitation documented by reverse-engineered integrations.
    pw = password[:25]

    login_url = f"{base_url.rstrip('/')}/api/user/appUserLogin"
    login_payload = http_post_form_json(
        login_url,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
        form_data={
            "appEmail": email,
            "appPasswordl": pw,
        },
        timeout=timeout,
    )

    if str(login_payload.get("code", "")) != "200":
        msg = str(login_payload.get("msg", "login failed"))
        raise ConnectorError("auth_failed", f"ACInfinity login failed: {msg}", retryable=False)

    data = login_payload.get("data", {})
    if not isinstance(data, dict):
        raise ConnectorError("schema_changed", "ACInfinity login response missing data object", retryable=False)

    app_id = str(data.get("appId", "")).strip()
    if not app_id:
        raise ConnectorError("schema_changed", "ACInfinity login response missing appId", retryable=False)

    return app_id, user_id or app_id


def _fetch_live(timeout: float) -> Dict[str, Any]:
    base_url = os.getenv("ACINFINITY_API_BASE", "http://www.acinfinityserver.com").strip()
    token, user_id = _resolve_auth(timeout=timeout, base_url=base_url)

    url = f"{base_url.rstrip('/')}/api/user/devInfoListAll"
    payload = http_post_form_json(
        url,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "token": token,
            "phoneType": os.getenv("ACINFINITY_PHONE_TYPE", "1").strip() or "1",
            "appVersion": os.getenv("ACINFINITY_APP_VERSION", "1.9.7").strip() or "1.9.7",
        },
        form_data={"userId": user_id},
        timeout=timeout,
    )

    code = str(payload.get("code", ""))
    if code not in {"200", "0"}:
        msg = str(payload.get("msg", "unknown ACInfinity error"))
        raise ConnectorError("auth_failed", f"ACInfinity dev list failed: {msg}", retryable=False)

    payload["_raw_ref"] = "acinfinity:devInfoListAll"
    return payload


def run() -> Dict[str, Any]:
    args = parse_args(SOURCE)
    ts = utc_now_iso()

    try:
        if args.mock:
            payload = load_json_file(Path(args.mock_file)) if args.mock_file else _built_in_mock()
        else:
            payload = _fetch_live(args.timeout)

        devices = _get_device_candidates(payload)
        if not devices:
            raise ConnectorError("schema_changed", "no devices in ACInfinity response", retryable=False)

        selected = _pick_device(devices)
        if not selected:
            raise ConnectorError("schema_changed", "failed to select ACInfinity device", retryable=False)

        selected_metrics, selected_device_id = _extract_device_metrics(selected, ts)
        selected_metrics = _select_canonical_metrics(selected, selected_metrics)
        if not selected_metrics:
            raise ConnectorError("schema_changed", "no expected metrics in ACInfinity payload", retryable=False)

        unit_map = {
            "air_temp_c": "C",
            "humidity_pct": "pct",
            "fan_speed_pct": "pct",
            "vpd_kpa": "kPa",
            "air_temp_outdoor_c": "C",
            "humidity_outdoor_pct": "pct",
            "vpd_outdoor_kpa": "kPa",
            "co2_ppm": "ppm",
            "light_pct": "pct",
        }
        metrics: List[Dict[str, Any]] = []
        for metric_name, unit in unit_map.items():
            if metric_name in selected_metrics:
                metrics.append(
                    {"metric": metric_name, "value": selected_metrics[metric_name], "unit": unit, "timestamp": ts}
                )
        metrics.append({"metric": "controller_device_id", "value": selected_device_id, "unit": "id", "timestamp": ts})

        role_overrides = _parse_role_overrides()
        device_entries: List[Dict[str, Any]] = []
        seen_roles: Set[str] = set()
        for idx, dev in enumerate(devices):
            entries, roles = _extract_component_entries(dev, ts=ts, role_overrides=role_overrides)
            if entries:
                device_entries.extend(entries)
                seen_roles.update(roles)
                continue
            mapped, device_id = _extract_device_metrics(dev, ts)
            role = _classify_role(dev, device_id=device_id, role_overrides=role_overrides)
            if role in EXPECTED_ROLES:
                seen_roles.add(role)
            if not mapped and role == "unbekannt":
                continue
            device_entries.append(
                {
                    "device_id": device_id,
                    "device_name": _device_name(dev, f"controller-{idx+1}"),
                    "source": SOURCE,
                    "role": role,
                    "metrics": mapped,
                    "timestamp": ts,
                }
            )

        names = {m.get("metric") for m in metrics}
        status = "ok" if {"air_temp_c", "humidity_pct"}.issubset(names) else "degraded"

        result: Dict[str, Any] = {
            "source": SOURCE,
            "status": status,
            "fetched_at": ts,
            "metrics": metrics,
            "devices": device_entries,
            "expected_roles": list(EXPECTED_ROLES),
            "missing_roles": [role for role in EXPECTED_ROLES if role not in seen_roles],
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
