# Usage: stack-bazarr-search-missing
# Triggers Bazarr's missing-subtitle search now instead of waiting for
# its own scheduler (default every 6h).
function stack-bazarr-search-missing --description 'Trigger an on-demand Bazarr missing-subtitle search'
    __stack_api POST "/api/bazarr/search-missing"
end
