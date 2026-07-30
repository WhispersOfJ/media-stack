# Usage: stack-wrapperr-links
# Public share links Wrapperr has generated for specific reports.
function stack-wrapperr-links --description 'List Wrapperr public share links'
    __stack_api GET /api/wrapperr/links
end
