# Usage: stack-plexanisync-run-now
# Starts an out-of-schedule anime watch-state push from Plex to AniList.
#
# Started, not finished. A full run walks both anime libraries and rate-limits
# against AniList's API, so this returns immediately and the outcome shows up
# in stack-plexanisync-last-run, not here.
#
# The scheduled runs (systemd/plexanisync.timer, 00:45/06:45/12:45/18:45) stay
# on regardless - this is a manual extra, not a replacement. A second run while
# one is already going is refused, not queued: two concurrent runs would push
# conflicting updates to the same AniList list.
function stack-plexanisync-run-now --description 'Start an out-of-schedule PlexAniSync sync to AniList'
    __stack_api POST /api/plexanisync/run-now '{}'
end
