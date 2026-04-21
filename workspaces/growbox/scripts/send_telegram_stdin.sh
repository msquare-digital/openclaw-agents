#!/usr/bin/env bash
set -euo pipefail

ACCOUNT="${1:-${GROWBOX_TELEGRAM_ACCOUNT:-growbox}}"
TARGET="${2:-${GROWBOX_TELEGRAM_TARGET:-}}"

if [[ -z "$TARGET" ]]; then
  echo "missing target chat id/username (arg2 or GROWBOX_TELEGRAM_TARGET)" >&2
  exit 2
fi

MSG="$(cat)"
if [[ -z "${MSG// }" ]]; then
  exit 0
fi

openclaw message send \
  --channel telegram \
  --account "$ACCOUNT" \
  --target "$TARGET" \
  --message "$MSG" \
  --json >/dev/null
