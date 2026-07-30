# Usage: stack-lingarr-recent-translations
# Recent individual translation-completed events pulled from container logs -
# distinct from stack-lingarr-stats' lifetime totals.
function stack-lingarr-recent-translations --description 'Show recent Lingarr translation events'
    __stack_api GET /api/lingarr/recent-translations
end
