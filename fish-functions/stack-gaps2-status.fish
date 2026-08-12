# Usage: stack-gaps2-status
# GAPS-2's current state: whether a sweep is running and which library it is
# on, plus when each library was last scanned and how many gaps it found.
# "Never scanned" is reported separately from "zero gaps" on purpose - a bare
# count of 0 reads the same for both, and they mean opposite things.
function stack-gaps2-status --description 'GAPS-2 scan state and last scan per library'
    __stack_api GET /api/gaps2/status
end
