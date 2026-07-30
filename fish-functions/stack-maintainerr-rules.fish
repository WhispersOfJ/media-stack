# Usage: stack-maintainerr-rules
# Configured Maintainerr rules - expected empty, see stack-maintainerr-safety-check.
function stack-maintainerr-rules --description 'List configured Maintainerr rules'
    __stack_api GET /api/maintainerr/rules
end
