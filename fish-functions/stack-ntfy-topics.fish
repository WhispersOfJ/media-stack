# Usage: stack-ntfy-topics
# Lists the ntfy topics this stack publishes to (Radarr/Sonarr/Prowlarr
# alerts, one topic per app) - not a live query against ntfy itself, which
# has no server-side "list all topics" API by design.
function stack-ntfy-topics --description 'List topics this stack publishes to on ntfy'
    __stack_api GET /api/ntfy/topics
end
