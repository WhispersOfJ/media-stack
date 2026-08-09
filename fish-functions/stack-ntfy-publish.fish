# Usage: stack-ntfy-publish <topic> <message>
# Publishes one message to one ntfy topic - see stack-ntfy-topics for the
# known topics this stack already publishes to.
function stack-ntfy-publish --description 'Publish a message to an ntfy topic'
    if test (count $argv) -ne 2
        echo "Usage: stack-ntfy-publish <topic> <message>" >&2
        return 1
    end
    set -l body (python3 -c "import json, sys; print(json.dumps({'topic': sys.argv[1], 'message': sys.argv[2]}))" "$argv[1]" "$argv[2]")
    __stack_api POST "/api/ntfy/publish" "$body"
end
