#!/usr/bin/env bash
# Daily backup of ./config (every app's settings/state/API keys - the one
# thing in this stack that isn't reproducible from git or a re-pull/re-scan).
# Run by systemd/stack-backup.{service,timer}. Repo lives outside git at
# ~/backups/stack-restic-repo (local disk only - see README's backup section
# for the single-disk caveat and cloud-remote upgrade path).
#
# Every restic call runs via sudo -n -E (passwordless, already configured on
# this host) - some Plex files are mode 600 under a uid this user can't
# read, and Plex recreates them with that same mode on every write so a
# one-time chmod doesn't stick. -E preserves RESTIC_REPOSITORY/
# RESTIC_PASSWORD_FILE into the root environment. Since root now owns
# every new object restic writes into the repo, every restic invocation
# against it - including a manual one-off check - needs sudo too, or it
# will fail to read/write repo objects the daily run already created.
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
  --exclude "config/*/logs"
  --exclude "config/*/log"
  --exclude "config/plex/Plex Media Server/Metadata"
  --exclude "config/plex/Plex Media Server/Cache"
  --exclude "config/plex/Plex Media Server/Codecs"
  --exclude "config/plex/Plex Media Server/Logs"
  --exclude "config/plex/Plex Media Server/Crash Reports"
  --exclude "config/plex-transcode"
)

# sudo -n -E (preserves RESTIC_REPOSITORY/RESTIC_PASSWORD_FILE): several
# Plex files (Preferences.xml, .LocalAdminToken) are mode 600 owned by
# whatever host account happens to share PLEX_UID=955's numeric id - not
# readable by this user, and Plex recreates them with the same restrictive
# mode on every write, so a one-time chmod doesn't stick. Same reasoning
# backup-claude-dir.sh already uses sudo -n tar for. Confirmed live: these
# files were silently missing from every snapshot (restic exit 3) until
# this was added.
sudo -n -E restic backup ./config "${RESTIC_EXCLUDES[@]}"
backup_status=$?

# Exit code 3 = "some source files could not be read" (locked/live files -
# e.g. sqlite -wal, an app mid-write). The snapshot it did produce is still
# good, so don't let that block retention pruning below. Anything else
# (1 = fatal error) should stop the script and surface as a failed run.
if [ "$backup_status" -ne 0 ] && [ "$backup_status" -ne 3 ]; then
  ./scripts/notify-discord.sh "Backup failed (restic exit $backup_status) - check \`journalctl --user -u stack-backup.service\`" error
  exit "$backup_status"
fi

if ! sudo -n -E restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune; then
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
#
# Unlike the local repo (which stays root-owned by design - see the module
# comment), this target lives inside a folder a user-level daemon (Dropbox)
# actively syncs. Root-owned files it can't read are invisible to it, and a
# sync client that finds it can't read/reconcile most of a folder's contents
# may fall back to treating it as empty rather than partially-synced -
# confirmed live: a completed 103GB backup here was wiped on both local disk
# and the Dropbox cloud side within two hours of being written root-owned,
# with no error surfaced anywhere. `chown` back to the invoking user
# immediately after every write/prune closes this - a later sudo restic call
# against this repo still works fine (root can always read a user-owned
# file), only the reverse (a non-root daemon reading a root-owned file)
# was ever the problem.
if [ -n "$BACKUP_REMOTE_REPOSITORY" ]; then
  (
    export RESTIC_REPOSITORY="$BACKUP_REMOTE_REPOSITORY"
    export RESTIC_PASSWORD_FILE="${BACKUP_REMOTE_PASSWORD_FILE:-$HOME/backups/.restic-password}"
    sudo -n -E restic backup ./config "${RESTIC_EXCLUDES[@]}"
    remote_status=$?
    sudo -n chown -R "$(id -u):$(id -g)" "$BACKUP_REMOTE_REPOSITORY"
    if [ "$remote_status" -ne 0 ] && [ "$remote_status" -ne 3 ]; then
      ./scripts/notify-discord.sh "Backup (remote) failed (restic exit $remote_status)" error
      exit "$remote_status"
    fi
    if ! sudo -n -E restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune; then
      ./scripts/notify-discord.sh "Backup (remote) snapshot succeeded but retention pruning failed" warn
      exit 1
    fi
    sudo -n chown -R "$(id -u):$(id -g)" "$BACKUP_REMOTE_REPOSITORY"
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
  if sudo -n -E restic check --read-data-subset=10%; then
    ./scripts/notify-discord.sh "Monthly restic integrity check passed (10% subset)" info
  else
    ./scripts/notify-discord.sh "Monthly restic integrity check FAILED - repo may be corrupted, verify before relying on it for a restore" error
  fi
  if [ -n "$BACKUP_REMOTE_REPOSITORY" ]; then
    (
      export RESTIC_REPOSITORY="$BACKUP_REMOTE_REPOSITORY"
      export RESTIC_PASSWORD_FILE="${BACKUP_REMOTE_PASSWORD_FILE:-$HOME/backups/.restic-password}"
      if sudo -n -E restic check --read-data-subset=10%; then
        ./scripts/notify-discord.sh "Monthly restic integrity check (remote) passed (10% subset)" info
      else
        ./scripts/notify-discord.sh "Monthly restic integrity check (remote) FAILED - repo may be corrupted" error
      fi
    )
  fi
fi
