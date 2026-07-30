# Usage: stack-maintainerr-plex-link-check
# Confirms Maintainerr's configured Plex host matches this stack's real Plex.
function stack-maintainerr-plex-link-check --description 'Check Maintainerr-Plex config drift'
    __stack_api GET /api/maintainerr/plex-link-check
end
