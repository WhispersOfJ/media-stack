# Usage: stack-checkrr-reacquire-guard
# Alerts if Checkrr's process:false flag is ever flipped to true for any
# Arr app - that flip enables auto-delete/reacquire (see CLAUDE.md).
function stack-checkrr-reacquire-guard --description 'Alert if Checkrr process flag is ever enabled'
    __stack_api GET /api/checkrr/reacquire-guard
end
