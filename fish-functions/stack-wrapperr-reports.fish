# Usage: stack-wrapperr-reports
# Saved report definitions from Wrapperr's config.json.
function stack-wrapperr-reports --description 'List Wrapperr saved reports'
    __stack_api GET /api/wrapperr/reports
end
