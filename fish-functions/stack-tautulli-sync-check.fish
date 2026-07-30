# Usage: stack-tautulli-sync-check
# Confirms Tautulli is tracking this stack's real Plex server, not a stale one.
function stack-tautulli-sync-check --description 'Check Tautulli-Plex config drift'
    __stack_api GET /api/tautulli/sync-check
end
