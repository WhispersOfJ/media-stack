# Usage: stack-kometa-run-now
# Triggers an immediate Kometa run alongside its own KOMETA_TIMES scheduler.
# Detached - returns right away, a full run can take minutes. Check with
# stack-kometa-logs or stack-kometa-last-run-result shortly after.
function stack-kometa-run-now --description 'Trigger an immediate Kometa run'
    __stack_api POST /api/kometa/run-now
end
