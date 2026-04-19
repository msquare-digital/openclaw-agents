#!/usr/bin/env python3
"""Shared helpers for GrowBox connectors."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from urllib import error, request


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json_file(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def parse_args(source_name: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"{source_name} connector")
    parser.add_argument("--mock", action="store_true", help="Use local mock data")
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--mock-file",
        default="",
        help="Optional JSON file to override built-in mock payload",
    )
    return parser.parse_args()


def _read_first_line(text: str) -> Optional[str]:
    line = text.strip().splitlines()
    if not line:
        return None
    value = line[0].strip()
    return value or None


def _read_secret_from_pass(entry: str) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["pass", "show", entry],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None

    if proc.returncode != 0:
        return None
    return _read_first_line(proc.stdout)


def read_secret_from_env_or_file(
    env_key: str,
    file_env_key: str,
    pass_env_key: str = "",
    default_pass_entry: str = "",
) -> Optional[str]:
    direct = os.getenv(env_key, "").strip()
    if direct:
        return direct

    file_path = os.getenv(file_env_key, "").strip()
    if file_path:
        p = Path(file_path)
        if p.exists():
            file_secret = p.read_text(encoding="utf-8").strip()
            if file_secret:
                return file_secret

    pass_entry = ""
    if pass_env_key:
        pass_entry = os.getenv(pass_env_key, "").strip()
    if not pass_entry:
        pass_entry = default_pass_entry.strip()
    if not pass_entry:
        return None

    return _read_secret_from_pass(pass_entry)


def safe_metric(value: Any, fallback: Optional[float] = None) -> Optional[float]:
    if value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def http_get_json(url: str, headers: Dict[str, str], timeout: float) -> Dict[str, Any]:
    req = request.Request(url, method="GET")
    for key, val in headers.items():
        req.add_header(key, val)

    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ConnectorError("auth_failed", f"HTTP {exc.code}", retryable=True) from exc
        if exc.code == 429:
            raise ConnectorError("rate_limited", "HTTP 429", retryable=True) from exc
        raise ConnectorError("api_unreachable", f"HTTP {exc.code}", retryable=True) from exc
    except error.URLError as exc:
        raise ConnectorError("api_unreachable", str(exc.reason), retryable=True) from exc
    except TimeoutError as exc:
        raise ConnectorError("api_unreachable", "timeout", retryable=True) from exc
    except json.JSONDecodeError as exc:
        raise ConnectorError("schema_changed", "invalid json response", retryable=False) from exc


def http_post_form_json(url: str, headers: Dict[str, str], form_data: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    encoded = urlencode(form_data).encode("utf-8")
    req = request.Request(url, data=encoded, method="POST")
    for key, val in headers.items():
        req.add_header(key, val)

    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ConnectorError("auth_failed", f"HTTP {exc.code}", retryable=True) from exc
        if exc.code == 429:
            raise ConnectorError("rate_limited", "HTTP 429", retryable=True) from exc
        raise ConnectorError("api_unreachable", f"HTTP {exc.code}", retryable=True) from exc
    except error.URLError as exc:
        raise ConnectorError("api_unreachable", str(exc.reason), retryable=True) from exc
    except TimeoutError as exc:
        raise ConnectorError("api_unreachable", "timeout", retryable=True) from exc
    except json.JSONDecodeError as exc:
        raise ConnectorError("schema_changed", "invalid json response", retryable=False) from exc


class ConnectorError(Exception):
    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def emit(result: Dict[str, Any], exit_code: int = 0) -> None:
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(exit_code)


def result_error(source: str, code: str, message: str, retryable: bool) -> Dict[str, Any]:
    return {
        "source": source,
        "status": "error",
        "fetched_at": utc_now_iso(),
        "metrics": [],
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
        },
    }
