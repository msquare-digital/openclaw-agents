#!/usr/bin/env bash
set -euo pipefail

PI_HOST="${PI_HOST:-msquare@dashboard}"
TARGET="${TARGET:-~/.openclaw}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

read -r -p "Deploy to PROD ($PI_HOST:$TARGET)? [y/N] " ans
if [[ "${ans:-}" != "y" && "${ans:-}" != "Y" ]]; then
  echo "Aborted."
  exit 1
fi

ssh "$PI_HOST" "mkdir -p $TARGET/agents/main/agent $TARGET/agents/mail/agent $TARGET/agents/pricewatch/agent $TARGET/workspace $TARGET/workspace/mail $TARGET/workspace-pricewatch"

rsync -az --delete "$ROOT/agents/main/agent/" "$PI_HOST:$TARGET/agents/main/agent/"
rsync -az --delete "$ROOT/agents/mail/agent/" "$PI_HOST:$TARGET/agents/mail/agent/"
rsync -az --delete "$ROOT/agents/pricewatch/agent/" "$PI_HOST:$TARGET/agents/pricewatch/agent/"

rsync -az --delete "$ROOT/workspaces/main/" "$PI_HOST:$TARGET/workspace/"
rsync -az --delete "$ROOT/workspaces/mail/" "$PI_HOST:$TARGET/workspace/mail/"
rsync -az --delete "$ROOT/workspaces/pricewatch/" "$PI_HOST:$TARGET/workspace-pricewatch/"

echo "Prod deploy done. Restart service manually if needed."
