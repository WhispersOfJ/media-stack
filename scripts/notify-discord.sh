#!/usr/bin/env bash
# Shared Discord webhook notifier - used by backup-config.sh,
# check-container-health.sh, and systemd's OnFailure= hook on any unit that
# wants one. Silently no-ops if DISCORD_WEBHOOK_URL isn't set/configured yet,
# so nothing breaks for anyone running this stack without alerting set up.
#
# Usage: notify-discord.sh "message text" [info|warn|error]
set -uo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] && set -a && source .env && set +a

message="${1:-}"
level="${2:-info}"

[ -z "${DISCORD_WEBHOOK_URL:-}" ] && exit 0
[ "$DISCORD_WEBHOOK_URL" = "changeme" ] && exit 0
[ -z "$message" ] && exit 0

case "$level" in
  error) prefix="🔴" ;;
  warn)  prefix="🟡" ;;
  *)     prefix="🟢" ;;
esac

payload=$(python3 -c "import json,sys; print(json.dumps({'content': sys.argv[1]}))" "$prefix **[${HOST_IP:-Stack}]** $message")

curl -s -o /dev/null -X POST -H "Content-Type: application/json" \
  -d "$payload" "$DISCORD_WEBHOOK_URL"
