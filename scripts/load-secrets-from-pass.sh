#!/usr/bin/env bash
set -euo pipefail

# Sync OpenClaw secrets from pass -> local secret files/runtime env.
# Optional: import inline secrets from openclaw.json into pass and sanitize config.

OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
SECRETS_DIR="$OPENCLAW_HOME/secrets"
RUNTIME_ENV_FILE="$SECRETS_DIR/runtime-secrets.env"
STRICT=0
PRINT_ONLY=0
IMPORT_CONFIG=""
SANITIZE_CONFIG=""

usage() {
  cat <<'EOF'
Usage:
  bash scripts/load-secrets-from-pass.sh [options]

Options:
  --openclaw-home <path>     Default: ~/.openclaw
  --strict                   Fail if a required pass entry is missing
  --print-only               Do not write files, only print actions
  --import-config <file>     Import inline secrets from openclaw.json into pass
  --sanitize-config <file>   Replace inline secrets in config with ${ENV_VAR} refs
  -h, --help                 Show help

Default pass entries used by this script:
  openrouter/api_key
  openclaw/gateway/token
  openai/whisper_api_key
  openclaw/telegram/default_bot_token (fallback: telegram/default/bot_token)
  openclaw/telegram/pricewatch_bot_token (fallback: telegram/pricewatch/bot_token)
  openclaw/telegram/growbox_bot_token (fallback: telegram/growbox/bot_token)

Outputs:
  ~/.openclaw/secrets/telegram-bot-token
  ~/.openclaw/secrets/telegram-pricewatch-bot-token
  ~/.openclaw/secrets/telegram-growbox-bot-token
  ~/.openclaw/secrets/runtime-secrets.env
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --openclaw-home)
      OPENCLAW_HOME="$2"
      SECRETS_DIR="$OPENCLAW_HOME/secrets"
      RUNTIME_ENV_FILE="$SECRETS_DIR/runtime-secrets.env"
      shift 2
      ;;
    --strict)
      STRICT=1
      shift
      ;;
    --print-only)
      PRINT_ONLY=1
      shift
      ;;
    --import-config)
      IMPORT_CONFIG="$2"
      shift 2
      ;;
    --sanitize-config)
      SANITIZE_CONFIG="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if ! command -v pass >/dev/null 2>&1; then
  echo "Error: 'pass' not found. Install pass + gpg first." >&2
  exit 1
fi

warn() { echo "WARN: $*" >&2; }
info() { echo "INFO: $*"; }

read_pass_first_line() {
  local entry="$1"
  local out
  if ! out="$(pass show "$entry" 2>/dev/null)"; then
    return 1
  fi
  printf '%s' "$out" | head -n1
}

read_pass_candidates() {
  local candidates="$1"
  local entry
  IFS='|' read -r -a entry <<<"$candidates"
  local value=""
  for c in "${entry[@]}"; do
    if value="$(read_pass_first_line "$c")"; then
      printf '%s\t%s' "$c" "$value"
      return 0
    fi
  done
  return 1
}

ensure_dirs() {
  if [[ "$PRINT_ONLY" -eq 1 ]]; then
    info "[print-only] mkdir -p $SECRETS_DIR"
    return
  fi
  mkdir -p "$SECRETS_DIR"
  chmod 700 "$SECRETS_DIR" || true
}

write_secret_file() {
  local file="$1"
  local value="$2"
  if [[ "$PRINT_ONLY" -eq 1 ]]; then
    info "[print-only] write file $file"
    return
  fi
  umask 077
  printf '%s\n' "$value" >"$file"
  chmod 600 "$file" || true
}

append_env_line() {
  local key="$1"
  local value="$2"
  local esc
  esc="$(printf '%s' "$value" | sed "s/'/'\\\\''/g")"
  printf "export %s='%s'\n" "$key" "$esc" >>"$RUNTIME_ENV_FILE"
}

import_config_to_pass() {
  local cfg="$1"
  if [[ ! -f "$cfg" ]]; then
    warn "--import-config file not found: $cfg"
    return 1
  fi
  info "Importing inline secrets from $cfg into pass (known keys only)..."
  python3 - "$cfg" <<'PY'
import json, sys
from pathlib import Path

cfg = Path(sys.argv[1])
obj = json.loads(cfg.read_text(encoding="utf-8"))

def get(path, default=""):
    cur = obj
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

pairs = [
    ("openrouter/api_key", get(["env", "OPENROUTER_API_KEY"], "")),
    ("openclaw/gateway/token", get(["gateway", "auth", "token"], "")),
    ("openai/whisper_api_key", get(["skills", "entries", "openai-whisper-api", "apiKey"], "")),
]

def usable(v):
    if not isinstance(v, str):
        return False
    t = v.strip()
    if not t:
        return False
    if t.startswith("<SET_") and t.endswith(">"):
        return False
    if t.startswith("${") and t.endswith("}"):
        return False
    return True

for entry, value in pairs:
    if usable(value):
        print(f"{entry}\t{value}")
PY
}

sanitize_config() {
  local cfg="$1"
  if [[ ! -f "$cfg" ]]; then
    warn "--sanitize-config file not found: $cfg"
    return 1
  fi
  info "Sanitizing inline secrets in $cfg -> env placeholders"
  if [[ "$PRINT_ONLY" -eq 1 ]]; then
    info "[print-only] would update env.OPENROUTER_API_KEY, gateway.auth.token, skills.entries.openai-whisper-api.apiKey"
    return 0
  fi

  python3 - "$cfg" <<'PY'
import json, sys
from pathlib import Path
cfg = Path(sys.argv[1])
obj = json.loads(cfg.read_text(encoding="utf-8"))

obj.setdefault("env", {})
obj["env"]["OPENROUTER_API_KEY"] = "${OPENROUTER_API_KEY}"
obj.setdefault("gateway", {}).setdefault("auth", {})
obj["gateway"]["auth"]["token"] = "${OPENCLAW_GATEWAY_TOKEN}"
obj.setdefault("skills", {}).setdefault("entries", {}).setdefault("openai-whisper-api", {})
obj["skills"]["entries"]["openai-whisper-api"]["apiKey"] = "${OPENAI_WHISPER_API_KEY}"

cfg.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

if [[ -n "$IMPORT_CONFIG" ]]; then
  imported=0
  while IFS=$'\t' read -r entry value; do
    [[ -z "$entry" ]] && continue
    info "pass insert -m -f $entry"
    if [[ "$PRINT_ONLY" -eq 0 ]]; then
      printf '%s\n' "$value" | pass insert -m -f "$entry" >/dev/null
    fi
    imported=$((imported + 1))
  done < <(import_config_to_pass "$IMPORT_CONFIG")
  info "Imported $imported secret(s) into pass."
fi

if [[ -n "$SANITIZE_CONFIG" ]]; then
  sanitize_config "$SANITIZE_CONFIG"
fi

ensure_dirs

if [[ "$PRINT_ONLY" -eq 1 ]]; then
  info "[print-only] write runtime env file $RUNTIME_ENV_FILE"
else
  : >"$RUNTIME_ENV_FILE"
  chmod 600 "$RUNTIME_ENV_FILE" || true
fi

# ENV exports (for placeholders in openclaw.json)
declare -a ENV_MAP=(
  "OPENROUTER_API_KEY|openrouter/api_key"
  "OPENCLAW_GATEWAY_TOKEN|openclaw/gateway/token"
  "OPENAI_WHISPER_API_KEY|openai/whisper_api_key"
)

missing=0
for item in "${ENV_MAP[@]}"; do
  key="${item%%|*}"
  entry="${item#*|}"
  if v="$(read_pass_first_line "$entry")"; then
    info "Loaded env secret $key from pass:$entry"
    if [[ "$PRINT_ONLY" -eq 0 ]]; then
      append_env_line "$key" "$v"
    fi
  else
    warn "Missing pass entry: $entry (for $key)"
    missing=$((missing + 1))
  fi
done

# Telegram token files
declare -a FILE_MAP=(
  "telegram-bot-token|openclaw/telegram/default_bot_token|telegram/default/bot_token"
  "telegram-pricewatch-bot-token|openclaw/telegram/pricewatch_bot_token|telegram/pricewatch/bot_token"
  "telegram-growbox-bot-token|openclaw/telegram/growbox_bot_token|telegram/growbox/bot_token"
)

for item in "${FILE_MAP[@]}"; do
  file_name="${item%%|*}"
  rest="${item#*|}"
  entry_primary="${rest%%|*}"
  entry_fallback="${rest#*|}"
  pair=""
  if pair="$(read_pass_candidates "$entry_primary|$entry_fallback")"; then
    used_entry="${pair%%$'\t'*}"
    value="${pair#*$'\t'}"
    info "Loaded file secret $file_name from pass:$used_entry"
    write_secret_file "$SECRETS_DIR/$file_name" "$value"
  else
    warn "Missing pass entry: $entry_primary (fallback: $entry_fallback)"
    missing=$((missing + 1))
  fi
done

cat <<EOF
Done.

Runtime env file:
  $RUNTIME_ENV_FILE

Before starting OpenClaw in this shell:
  source "$RUNTIME_ENV_FILE"

Optional hardening flow:
  bash scripts/load-secrets-from-pass.sh --import-config ~/.openclaw/openclaw.json --sanitize-config ~/.openclaw/openclaw.json
EOF

if [[ "$STRICT" -eq 1 && "$missing" -gt 0 ]]; then
  echo "Error: missing $missing required pass entries." >&2
  exit 3
fi

