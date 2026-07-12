#!/usr/bin/env bash
# Daily backup of ./config (every app's settings/state/API keys - the one
# thing in this stack that isn't reproducible from git or a re-pull/re-scan).
# Run by systemd/stack-backup.{service,timer}. Repo lives outside git at
# ~/backups/stack-restic-repo (local disk only - see README's backup section
# for the single-disk caveat and cloud-remote upgrade path).
set -uo pipefail

cd "$(dirname "$0")/.." || exit

# Deliberately not `source .env` - see notify-discord.sh's own comment on why
# (literal `$` in some values breaks bash's assignment expansion under set -u).
env_get() { [ -f .env ] && grep -E "^${1}=" .env | head -1 | cut -d'=' -f2-; }
BACKUP_REMOTE_REPOSITORY="$(env_get BACKUP_REMOTE_REPOSITORY)"
BACKUP_REMOTE_PASSWORD_FILE="$(env_get BACKUP_REMOTE_PASSWORD_FILE)"

export RESTIC_REPOSITORY="$HOME/backups/stack-restic-repo"
export RESTIC_PASSWORD_FILE="$HOME/backups/.restic-password"

RESTIC_EXCLUDES=(
  --exclude "config/decypharr/cache"
  --exclude "config/*/logs"
  --exclude "config/*/log"
  --exclude "config/zilean-postgres"
  --exclude "config/dmm-mysql"
  --exclude "config/plex/Plex Media Server/Metadata"
  --exclude "config/plex/Plex Media Server/Cache"
  --exclude "config/plex/Plex Media Server/Codecs"
  --exclude "config/plex/Plex Media Server/Logs"
  --exclude "config/plex/Plex Media Server/Crash Reports"
  --exclude "config/plex-transcode"
  # Same "regenerable, don't bother backing it up" reasoning as Plex's own
  # Cache/Codecs exclusions above - cache and generated are fully rebuilt by
  # re-running Scan/Generate against the still-real source library; blobs
  # (scene covers) and metadata (config/scraped data) are the only Stash
  # subdirs actually worth restoring.
  --exclude "config/stash/cache"
  --exclude "config/stash/generated"
)

# Logical dump of zilean-postgres before the restic run below - the raw
# datadir is excluded (a live raw-file backup of postgres would be
# inconsistent) but nothing else covered that gap, so the ~5,600-entry
# Real-Debrid-ingested hash index had zero backup coverage. Separate
# directory name from the excluded config/zilean-postgres path so it's
# unambiguously not caught by that --exclude below.
mkdir -p ./config/zilean-postgres-dump
if ! docker exec zilean-postgres pg_dump -U postgres zilean | gzip > ./config/zilean-postgres-dump/zilean.sql.gz; then
  ./scripts/notify-discord.sh "zilean-postgres logical dump failed - config backup below will still run, but the postgres index itself won't be covered by this snapshot" warn
fi

# Same gap, same fix, for dmm-mysql - closed proactively this time instead of
# discovered missing later. Only runs if the container exists (extras profile).
if docker inspect dmm-mysql >/dev/null 2>&1; then
  mkdir -p ./config/dmm-mysql-dump
  if ! docker exec dmm-mysql sh -c 'exec mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" dmm' | gzip > ./config/dmm-mysql-dump/dmm.sql.gz; then
    ./scripts/notify-discord.sh "dmm-mysql logical dump failed - config backup below will still run, but DebridMediaManager's database won't be covered by this snapshot" warn
  fi
fi

restic backup ./config "${RESTIC_EXCLUDES[@]}"
backup_status=$?

# Exit code 3 = "some source files could not be read" (locked/live files -
# e.g. sqlite -wal, an app mid-write). The snapshot it did produce is still
# good, so don't let that block retention pruning below. Anything else
# (1 = fatal error) should stop the script and surface as a failed run.
if [ "$backup_status" -ne 0 ] && [ "$backup_status" -ne 3 ]; then
  ./scripts/notify-discord.sh "Backup failed (restic exit $backup_status) - check \`journalctl --user -u stack-backup.service\`" error
  exit "$backup_status"
fi

if ! restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune; then
  ./scripts/notify-discord.sh "Backup snapshot succeeded but retention pruning failed - check \`journalctl --user -u stack-backup.service\`" warn
  exit 1
fi

# Exit code 3 during the backup itself is worth a heads-up (not fatal, but
# something was skipped) even though the run overall succeeded.
if [ "$backup_status" -eq 3 ]; then
  ./scripts/notify-discord.sh "Backup completed with some files unreadable (exit 3 - likely a live/locked file, snapshot is still good)" warn
else
  ./scripts/notify-discord.sh "Backup completed successfully" info
fi

# Off-site leg - skipped entirely unless BACKUP_REMOTE_REPOSITORY is set (see
# .env.example's "Off-site backup" section). Same exclude list, own retention
# pass, tagged "(remote)" in every notification so a local-only failure and a
# remote-only failure are never confused with each other.
if [ -n "$BACKUP_REMOTE_REPOSITORY" ]; then
  (
    export RESTIC_REPOSITORY="$BACKUP_REMOTE_REPOSITORY"
    export RESTIC_PASSWORD_FILE="${BACKUP_REMOTE_PASSWORD_FILE:-$HOME/backups/.restic-password}"
    restic backup ./config "${RESTIC_EXCLUDES[@]}"
    remote_status=$?
    if [ "$remote_status" -ne 0 ] && [ "$remote_status" -ne 3 ]; then
      ./scripts/notify-discord.sh "Backup (remote) failed (restic exit $remote_status)" error
      exit "$remote_status"
    fi
    if ! restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune; then
      ./scripts/notify-discord.sh "Backup (remote) snapshot succeeded but retention pruning failed" warn
      exit 1
    fi
    if [ "$remote_status" -eq 3 ]; then
      ./scripts/notify-discord.sh "Backup (remote) completed with some files unreadable (exit 3, snapshot still good)" warn
    else
      ./scripts/notify-discord.sh "Backup (remote) completed successfully" info
    fi
  )
fi

# Monthly integrity check (1st of the month, piggybacking on this same daily
# trigger rather than a separate timer) - a corrupted repo should be caught
# before the day it's actually needed for a restore, not after.
if [ "$(date +%d)" = "01" ]; then
  if restic check --read-data-subset=10%; then
    ./scripts/notify-discord.sh "Monthly restic integrity check passed (10% subset)" info
  else
    ./scripts/notify-discord.sh "Monthly restic integrity check FAILED - repo may be corrupted, verify before relying on it for a restore" error
  fi
  if [ -n "$BACKUP_REMOTE_REPOSITORY" ]; then
    (
      export RESTIC_REPOSITORY="$BACKUP_REMOTE_REPOSITORY"
      export RESTIC_PASSWORD_FILE="${BACKUP_REMOTE_PASSWORD_FILE:-$HOME/backups/.restic-password}"
      if restic check --read-data-subset=10%; then
        ./scripts/notify-discord.sh "Monthly restic integrity check (remote) passed (10% subset)" info
      else
        ./scripts/notify-discord.sh "Monthly restic integrity check (remote) FAILED - repo may be corrupted" error
      fi
    )
  fi
fi
