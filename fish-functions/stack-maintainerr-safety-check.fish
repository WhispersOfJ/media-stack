# Usage: stack-maintainerr-safety-check
# Alerts if Maintainerr ever has an active rule - it was installed with
# zero rules on purpose, given this stack's mass-deletion history.
function stack-maintainerr-safety-check --description 'Alert if any Maintainerr rule is active'
    __stack_api GET /api/maintainerr/safety-check
end
