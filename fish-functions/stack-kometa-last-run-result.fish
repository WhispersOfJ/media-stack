# Usage: stack-kometa-last-run-result
# Scans further back through logs for the last completed run's outcome -
# a summary line, or a traceback if it errored - distinct from stack-kometa-status.
function stack-kometa-last-run-result --description 'Show outcome of the last completed Kometa run'
    __stack_api GET /api/kometa/last-run-result
end
