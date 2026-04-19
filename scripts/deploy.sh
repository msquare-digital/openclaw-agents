#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<USAGE
Usage:
  $(basename "$0") [--env dev|prod] [--all | --agent <id> ...] [--host <user@host>] [--target <path>] [--yes]
  $(basename "$0") --list

Examples:
  $(basename "$0") --env dev --all
  $(basename "$0") --env dev --agent mail
  $(basename "$0") --env prod --agent pricewatch --yes
USAGE
}

ENVIRONMENT="dev"
PI_HOST="${PI_HOST:-msquare@dashboard}"
TARGET=""
AUTO_YES="false"
LIST_ONLY="false"
ALL_AGENTS="false"
declare -a AGENTS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENVIRONMENT="${2:-}"
      shift 2
      ;;
    --host)
      PI_HOST="${2:-}"
      shift 2
      ;;
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    --agent)
      AGENTS+=("${2:-}")
      shift 2
      ;;
    --all)
      ALL_AGENTS="true"
      shift
      ;;
    --yes|-y)
      AUTO_YES="true"
      shift
      ;;
    --list)
      LIST_ONLY="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  echo "--env must be dev or prod" >&2
  exit 1
fi

if [[ -z "$TARGET" ]]; then
  if [[ "$ENVIRONMENT" == "dev" ]]; then
    TARGET="~/.openclaw-dev"
  else
    TARGET="~/.openclaw"
  fi
fi

if [[ "$LIST_ONLY" == "true" ]]; then
  find "$ROOT/agents" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort
  exit 0
fi

if [[ "$ALL_AGENTS" == "true" && ${#AGENTS[@]} -gt 0 ]]; then
  echo "Use either --all or --agent, not both." >&2
  exit 1
fi

if [[ "$ALL_AGENTS" == "true" ]]; then
  mapfile -t AGENTS < <(find "$ROOT/agents" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort)
fi

if [[ ${#AGENTS[@]} -eq 0 ]]; then
  echo "No agents selected. Use --all or --agent <id>." >&2
  exit 1
fi

if [[ "$ENVIRONMENT" == "prod" && "$AUTO_YES" != "true" ]]; then
  read -r -p "Deploy to PROD ($PI_HOST:$TARGET)? [y/N] " ans
  if [[ "${ans:-}" != "y" && "${ans:-}" != "Y" ]]; then
    echo "Aborted."
    exit 1
  fi
fi

unique_agents=()
seen_agents=" "
for id in "${AGENTS[@]}"; do
  if [[ -z "$id" ]]; then
    continue
  fi
  if [[ "$seen_agents" != *" $id "* ]]; then
    unique_agents+=("$id")
    seen_agents+="$id "
  fi
done

workspace_target_for_agent() {
  local id="$1"
  if [[ "$id" == "main" ]]; then
    echo "$TARGET/workspace"
    return 0
  fi

  if ssh "$PI_HOST" "[ -d $TARGET/workspace-$id ]" >/dev/null 2>&1; then
    echo "$TARGET/workspace-$id"
  else
    echo "$TARGET/workspace/$id"
  fi
}

echo "Deploy environment: $ENVIRONMENT"
echo "Remote: $PI_HOST:$TARGET"
echo "Agents: ${unique_agents[*]}"

for id in "${unique_agents[@]}"; do
  local_agent_dir="$ROOT/agents/$id/agent"
  local_workspace_dir="$ROOT/workspaces/$id"

  if [[ ! -d "$local_agent_dir" ]]; then
    echo "Skip '$id': missing $local_agent_dir" >&2
    continue
  fi

  remote_agent_dir="$TARGET/agents/$id/agent"
  remote_workspace_dir="$(workspace_target_for_agent "$id")"

  ssh "$PI_HOST" "mkdir -p $remote_agent_dir"
  rsync -az --delete "$local_agent_dir/" "$PI_HOST:$remote_agent_dir/"

  if [[ -d "$local_workspace_dir" ]]; then
    ssh "$PI_HOST" "mkdir -p $remote_workspace_dir"
    rsync -az --delete "$local_workspace_dir/" "$PI_HOST:$remote_workspace_dir/"
  else
    echo "Skip workspace for '$id': missing $local_workspace_dir"
  fi

  echo "Deployed agent '$id'"
done

echo "Done. openclaw config file and secrets are intentionally not overwritten."
