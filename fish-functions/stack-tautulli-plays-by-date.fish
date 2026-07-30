# Usage: stack-tautulli-plays-by-date [days]
# Daily play-count trend for the last N days (default 30).
function stack-tautulli-plays-by-date --description 'Show Tautulli plays-by-date trend'
    set -l days 30
    test (count $argv) -ge 1; and set days $argv[1]
    __stack_api GET "/api/tautulli/plays-by-date?days=$days"
end
