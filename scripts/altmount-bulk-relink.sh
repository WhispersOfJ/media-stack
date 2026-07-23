#!/usr/bin/env bash
# Bulk re-link: resubmits every existing radarr/sonarr NZB (extracted from
# NzbDAV's own blob store) to AltMount, so its own mount picks up the
# existing library instead of just future grabs. See CLAUDE.md's AltMount
# section for why this exists and the real scale involved (~38,972 releases).
#
# Resumable: progress is tracked in $PROGRESS_FILE, one line per attempted
# blob id. Re-running this script skips anything already recorded there.
set -uo pipefail

LIST_FILE="/tmp/altmount_relink_list.txt"
PROGRESS_FILE="/home/bear/Claude/media-stack/scripts/.altmount-relink-progress.log"
BLOB_ROOT="/home/bear/Claude/media-stack/config/nzbdav/blobs"
ALTMOUNT_URL="http://192.168.4.105:8081"
API_KEY="R1yPWsTObHXjkz5lSkDj0qbltLKbzt4L"
TMP_NZB="/tmp/altmount-relink-current.nzb"

touch "$PROGRESS_FILE"

total=$(wc -l < "$LIST_FILE")
done_count=0
ok_count=0
fail_count=0
skip_count=0

while IFS='|' read -r blob_id category; do
  if grep -q "^${blob_id}|" "$PROGRESS_FILE" 2>/dev/null; then
    skip_count=$((skip_count+1))
    continue
  fi

  lower=$(echo "$blob_id" | tr 'A-Z' 'a-z')
  p1=${lower:0:2}
  p2=${lower:2:2}
  blob_path="$BLOB_ROOT/$p1/$p2/$lower"

  if [ ! -f "$blob_path" ]; then
    echo "${blob_id}|MISSING_BLOB" >> "$PROGRESS_FILE"
    fail_count=$((fail_count+1))
    done_count=$((done_count+1))
    continue
  fi

  sudo cp "$blob_path" "$TMP_NZB" 2>/dev/null
  sudo chmod 644 "$TMP_NZB" 2>/dev/null

  resp=$(curl -s -X POST "$ALTMOUNT_URL/sabnzbd?mode=addfile&apikey=$API_KEY&cat=$category" \
    -F "name=@$TMP_NZB;filename=${blob_id}.nzb" \
    --max-time 30)

  if echo "$resp" | grep -q '"status":true'; then
    echo "${blob_id}|OK" >> "$PROGRESS_FILE"
    ok_count=$((ok_count+1))
  else
    echo "${blob_id}|FAIL|$resp" >> "$PROGRESS_FILE"
    fail_count=$((fail_count+1))
  fi
  done_count=$((done_count+1))

  # Modest pacing - avoid hammering AltMount's SQLite writes and the HTTP
  # layer; the importer's own 2 workers + bounded NNTP pool are the real
  # throttle, this just keeps submissions from bursting faster than that.
  sleep 0.3

  if [ $((done_count % 200)) -eq 0 ]; then
    echo "PROGRESS: $done_count/$total submitted (ok=$ok_count fail=$fail_count skipped=$skip_count)"
  fi
done < "$LIST_FILE"

echo "RELINK COMPLETE: $done_count/$total processed (ok=$ok_count fail=$fail_count skipped=$skip_count)"
