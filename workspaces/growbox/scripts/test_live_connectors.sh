#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-}"
TIMEOUT_DEFAULT="${GROWBOX_CONNECTOR_TIMEOUT:-12}"

if [[ -n "$ENV_FILE" ]]; then
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "Missing env file: $ENV_FILE" >&2
    echo "Create it from: $ROOT/config/live.env.example" >&2
    exit 1
  fi
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

require_var() {
  local key="$1"
  local val="${!key:-}"
  if [[ -z "$val" ]]; then
    echo "Missing required var: $key" >&2
    return 1
  fi
}

require_var ACINFINITY_API_BASE
require_var ECOWITT_API_BASE

require_secret_source() {
  local token_key="$1"
  local file_key="$2"
  local pass_key="$3"
  local token_val="${!token_key:-}"
  local file_val="${!file_key:-}"
  local pass_val="${!pass_key:-}"

  local count=0
  [[ -n "$token_val" ]] && count=$((count + 1))
  [[ -n "$file_val" ]] && count=$((count + 1))
  [[ -n "$pass_val" ]] && count=$((count + 1))

  if [[ "$count" -gt 1 ]]; then
    echo "Set only one of $token_key, $file_key, $pass_key." >&2
    return 1
  fi
  if [[ "$count" -eq 0 ]]; then
    echo "Set one of $token_key, $file_key, $pass_key." >&2
    return 1
  fi
  if [[ -n "$file_val" && ! -f "$file_val" ]]; then
    echo "Token file does not exist: $file_val" >&2
    return 1
  fi
}

has_secret_source() {
  local token_key="$1"
  local file_key="$2"
  local pass_key="$3"
  local token_val="${!token_key:-}"
  local file_val="${!file_key:-}"
  local pass_val="${!pass_key:-}"
  [[ -n "$token_val" || -n "$file_val" || -n "$pass_val" ]]
}

if ! has_secret_source ACINFINITY_TOKEN ACINFINITY_TOKEN_FILE ACINFINITY_TOKEN_PASS_ENTRY; then
  # Token not set -> require email/password source pair.
  require_secret_source ACINFINITY_EMAIL ACINFINITY_EMAIL_FILE ACINFINITY_EMAIL_PASS_ENTRY
  require_secret_source ACINFINITY_PASSWORD ACINFINITY_PASSWORD_FILE ACINFINITY_PASSWORD_PASS_ENTRY
fi
require_secret_source ECOWITT_APPLICATION_KEY ECOWITT_APPLICATION_KEY_FILE ECOWITT_APPLICATION_KEY_PASS_ENTRY
require_secret_source ECOWITT_API_KEY ECOWITT_API_KEY_FILE ECOWITT_API_KEY_PASS_ENTRY
require_secret_source ECOWITT_MAC ECOWITT_MAC_FILE ECOWITT_MAC_PASS_ENTRY

echo "[1/3] ACInfinity connector"
python3 "$ROOT/scripts/connectors/acinfinity_connector.py" --timeout "$TIMEOUT_DEFAULT"

echo

echo "[2/3] Ecowitt connector"
python3 "$ROOT/scripts/connectors/ecowitt_connector.py" --timeout "$TIMEOUT_DEFAULT"

echo

echo "[3/3] Combined snapshot"
python3 "$ROOT/scripts/poll_growbox.py" --timeout "$TIMEOUT_DEFAULT"
