#!/usr/bin/env python3
"""ACInfinity cloud read-only connector for GrowBox monitoring."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

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


def _to_metrics(payload: Dict[str, Any], ts: str) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []

    devices = _get_device_candidates(payload)
    selected = _pick_device(devices)
    if not selected:
        raise ConnectorError("schema_changed", "no devices in ACInfinity response", retryable=False)

    temp_val: Optional[float] = None
    humidity_val: Optional[float] = None
    speed_pct_val: Optional[float] = None

    for key, val in _iter_key_values(selected):
        k = key.lower()
        if temp_val is None and k in {"temperature", "temperature_c", "temp"}:
            temp_val = _normalize_temperature(val)
        if humidity_val is None and k in {"humidity", "humidity_pct", "humi"}:
            humidity_val = _normalize_humidity(val)
        if speed_pct_val is None and k in {"speak", "onspead", "onselfspead", "fanspeed", "fan_speed"}:
            speed_pct_val = _normalize_speed_to_pct(val)

    if temp_val is not None:
        metrics.append({"metric": "air_temp_c", "value": temp_val, "unit": "C", "timestamp": ts})
    if humidity_val is not None:
        metrics.append({"metric": "humidity_pct", "value": humidity_val, "unit": "pct", "timestamp": ts})
    if speed_pct_val is not None:
        metrics.append({"metric": "fan_speed_pct", "value": speed_pct_val, "unit": "pct", "timestamp": ts})

    # Useful trace for debugging which device was chosen.
    for key in ("devId", "deviceId", "id"):
        ident = selected.get(key)
        if ident:
            metrics.append({"metric": "controller_device_id", "value": str(ident), "unit": "id", "timestamp": ts})
            break

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

        metrics = _to_metrics(payload, ts)
        if not metrics:
            raise ConnectorError("schema_changed", "no expected metrics in ACInfinity payload", retryable=False)

        names = {m.get("metric") for m in metrics}
        status = "ok" if {"air_temp_c", "humidity_pct"}.issubset(names) else "degraded"

        result: Dict[str, Any] = {
            "source": SOURCE,
            "status": status,
            "fetched_at": ts,
            "metrics": metrics,
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
