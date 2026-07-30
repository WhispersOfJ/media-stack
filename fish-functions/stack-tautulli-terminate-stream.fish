# Usage: stack-tautulli-terminate-stream <session_key>
# Kills a single active Plex stream by session_key (see stack-tautulli-activity).
function stack-tautulli-terminate-stream --description 'Terminate a Plex stream via Tautulli'
    if test (count $argv) -ne 1
        echo "Usage: stack-tautulli-terminate-stream <session_key>" >&2
        return 1
    end
    __stack_api POST "/api/tautulli/terminate-stream?session_key=$argv[1]"
end
