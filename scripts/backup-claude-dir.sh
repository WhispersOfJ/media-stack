#!/usr/bin/env bash
# Nightly full-tree snapshot of ~/Claude (everything under it, not just
# ./config) to the local Dropbox folder. Deliberately separate from
# backup-config.sh's restic run: that one is the real incremental/retained
# backup of ./config specifically; this is a cruder whole-directory tar,
# overwritten in place each run (not dated copies) so Dropbox usage doesn't
# grow unbounded. Needs sudo (passwordless, already configured on this host)
# since the tree includes container-owned files a normal user can't read.
set -uo pipefail

cd "$(dirname "$0")/.." || exit

DEST="$HOME/Dropbox/Claude-backup-latest.tar.zst"
TMP="${DEST}.tmp"

# media-stack/config (100GB of this tree's ~124GB) is already covered by
# backup-config.sh's restic run with real retention - duplicating it here
# was most of this script's runtime and the main source of the "changed
# mid-archive" race below, for a copy this script doesn't even retain
# (single overwritten .tmp, see the module comment above).
sudo -n tar --zstd -cf "$TMP" --exclude="Claude/media-stack/config" -C "$HOME" Claude
status=$?

# tar exit 1 = "some files changed while being archived" - not fatal, the
# archive is still complete and usable, just possibly inconsistent for the
# handful of files that were mid-write. Near-guaranteed every run given this
# tree includes live Docker container config/database files being written
# to constantly during the ~20-50 minutes this tar takes. Only exit codes
# >=2 (genuine fatal errors) should discard the archive - this mirrors
# backup-config.sh's own tolerance for restic's analogous exit code 3.
if [ "$status" -eq 0 ] || [ "$status" -eq 1 ]; then
  sudo -n chown "$(id -u):$(id -g)" "$TMP"
  mv -f "$TMP" "$DEST"
  if [ "$status" -eq 0 ]; then
    ./scripts/notify-discord.sh "Claude dir backup completed successfully ($(du -h "$DEST" | cut -f1))" info
  else
    ./scripts/notify-discord.sh "Claude dir backup completed (some live files changed mid-archive, tar exit 1 - archive is still complete) ($(du -h "$DEST" | cut -f1))" warn
  fi
else
  rm -f "$TMP"
  ./scripts/notify-discord.sh "Claude dir backup failed (tar exit $status) - check \`journalctl --user -u stack-claude-backup.service\`" error
  exit "$status"
fi
