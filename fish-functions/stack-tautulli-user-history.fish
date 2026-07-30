# Usage: stack-tautulli-user-history <user_id> [limit]
# Watch history filtered to one user_id (see stack-tautulli-users).
function stack-tautulli-user-history --description 'Show watch history for one Tautulli user'
    if test (count $argv) -lt 1
        echo "Usage: stack-tautulli-user-history <user_id> [limit]" >&2
        return 1
    end
    set -l limit 20
    test (count $argv) -ge 2; and set limit $argv[2]
    __stack_api GET "/api/tautulli/user-history?user_id=$argv[1]&limit=$limit"
end
