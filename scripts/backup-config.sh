#!/usr/bin/env bash
# Daily backup of ./config (every app's settings/state/API keys - the one
# thing in this stack that isn't reproducible from git or a re-pull/re-scan).
# Run by systemd/stack-backup.{service,timer}. Repo lives outside git at
# ~/backups/stack-restic-repo (local disk only - see README's backup section
# for the single-disk caveat and cloud-remote upgrade path).
set -uo pipefail

export RESTIC_REPOSITORY="$HOME/backups/stack-restic-repo"
export RESTIC_PASSWORD_FILE="$HOME/backups/.restic-password"

cd "$(dirname "$0")/.."

restic backup ./config \
  --exclude "config/decypharr/cache" \
  --exclude "config/recyclarr/resources" \
  --exclude "config/*/logs" \
  --exclude "config/*/log" \
  --exclude "config/zilean-postgres"
backup_status=$?

# Exit code 3 = "some source files could not be read" (locked/live files -
# e.g. sqlite -wal, an app mid-write). The snapshot it did produce is still
# good, so don't let that block retention pruning below. Anything else
# (1 = fatal error) should stop the script and surface as a failed run.
if [ "$backup_status" -ne 0 ] && [ "$backup_status" -ne 3 ]; then
  exit "$backup_status"
fi

restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
