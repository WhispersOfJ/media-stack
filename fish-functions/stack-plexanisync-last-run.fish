# Usage: stack-plexanisync-last-run
# Outcome of the most recent PlexAniSync sync: when it ran, how it exited, how
# many titles it matched, and a tail of its log.
#
# PlexAniSync has no API and no persistent process - it is a container that
# runs once and exits - so this reads the container's own exit state and logs.
# Sitting in Exited(0) between runs is the normal, healthy state.
#
# Watch for token_expired=true: the AniList token is a 1-year OAuth token with
# no non-interactive renewal, and an expired one is the failure this sync is
# most likely to hit. See STACK.md's PlexAniSync entry.
function stack-plexanisync-last-run --description 'Last PlexAniSync run: time, exit code, matched count'
    __stack_api GET /api/plexanisync/last-run
end
