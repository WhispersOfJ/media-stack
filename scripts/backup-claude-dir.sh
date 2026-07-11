#!/usr/bin/env bash
# Nightly full-tree snapshot of ~/Claude (everything under it, not just
# ./config) to the local Dropbox folder. Deliberately separate from
# backup-config.sh's restic run: that one is the real incremental/retained
# backup of ./config specifically; this is a cruder whole-directory tar,
# overwritten in place each run (not dated copies) so Dropbox usage doesn't
# grow unbounded. Needs sudo (passwordless, already configured on this host)
# since the tree includes container-owned files (dmm-mysql/zilean-postgres
# data dirs) a normal user can't read.
set -uo pipefail

cd "$(dirname "$0")/.." || exit

DEST="$HOME/Dropbox/Claude-backup-latest.tar.zst"
TMP="${DEST}.tmp"

if sudo -n tar --zstd -cf "$TMP" -C "$HOME" Claude; then
  sudo -n chown "$(id -u):$(id -g)" "$TMP"
  mv -f "$TMP" "$DEST"
  ./scripts/notify-discord.sh "Claude dir backup completed successfully ($(du -h "$DEST" | cut -f1))" info
else
  status=$?
  rm -f "$TMP"
  ./scripts/notify-discord.sh "Claude dir backup failed (tar exit $status) - check \`journalctl --user -u stack-claude-backup.service\`" error
  exit "$status"
fi
