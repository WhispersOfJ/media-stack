# Usage: stack-tautulli-stats
# Home-page stat cards (top movies/shows/users) - Tautulli's own dashboard summary.
function stack-tautulli-stats --description 'Show Tautulli home stats'
    __stack_api GET /api/tautulli/stats
end
