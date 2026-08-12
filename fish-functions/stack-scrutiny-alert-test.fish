# Usage: stack-scrutiny-alert-test
# Fires Scrutiny's own test notification through its configured notify.urls,
# which in this stack is the ntfy sink from Phase 1 (topic scrutiny-alerts).
# Proves the disk-failure alert path works without waiting for a real failure.
function stack-scrutiny-alert-test --description "Fire Scrutiny's test notification through ntfy"
    __stack_api POST /api/scrutiny/alert-test
end
