#!/usr/bin/env bash
# Polls docker for unhealthy/restarting containers and posts to Discord only
# on a *change* in the unhealthy set (new failure, or recovery) - not on
# every poll, so a container stuck unhealthy for hours doesn't spam.
# Run periodically by systemd/stack-health-check.{service,timer}.
set -uo pipefail

cd "$(dirname "$0")/.."

state_file="$HOME/.cache/stack-unhealthy-containers"
mkdir -p "$(dirname "$state_file")"
[ -f "$state_file" ] || touch "$state_file"

current=$(docker ps -a --filter "health=unhealthy" --filter "status=restarting" --format '{{.Names}}' | sort -u)
previous=$(cat "$state_file")

if [ "$current" = "$previous" ]; then
  exit 0
fi

newly_bad=$(comm -13 <(echo "$previous") <(echo "$current") 2>/dev/null | grep -v '^$' || true)
recovered=$(comm -23 <(echo "$previous") <(echo "$current") 2>/dev/null | grep -v '^$' || true)

if [ -n "$newly_bad" ]; then
  ./scripts/notify-discord.sh "Container(s) unhealthy/restarting: $(echo "$newly_bad" | tr '\n' ' ')" error
fi
if [ -n "$recovered" ]; then
  ./scripts/notify-discord.sh "Container(s) recovered: $(echo "$recovered" | tr '\n' ' ')" info
fi

echo "$current" > "$state_file"
