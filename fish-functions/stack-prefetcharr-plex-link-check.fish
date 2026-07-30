# Usage: stack-prefetcharr-plex-link-check
# Confirms Prefetcharr's baked-in Plex URL still matches this stack's live PLEX_URL.
function stack-prefetcharr-plex-link-check --description 'Check Prefetcharr-Plex config drift'
    __stack_api GET /api/prefetcharr/plex-link-check
end
