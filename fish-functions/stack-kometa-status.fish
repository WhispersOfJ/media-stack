# Usage: stack-kometa-status
# Parses Kometa's own countdown log line for its next scheduled run time.
function stack-kometa-status --description 'Show time until next scheduled Kometa run'
    __stack_api GET /api/kometa/status
end
