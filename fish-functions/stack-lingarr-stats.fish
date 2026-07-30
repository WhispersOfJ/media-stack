# Usage: stack-lingarr-stats
# Lifetime translation totals - Lingarr's own dashboard summary.
function stack-lingarr-stats --description 'Show Lingarr lifetime translation stats'
    __stack_api GET /api/lingarr/stats
end
