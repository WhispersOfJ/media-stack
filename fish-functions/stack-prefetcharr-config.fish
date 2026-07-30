# Usage: stack-prefetcharr-config
# Effective PREFETCHARR_CONFIG (interval/prefetch_num/etc) from the running container.
function stack-prefetcharr-config --description 'Show effective Prefetcharr config'
    __stack_api GET /api/prefetcharr/config
end
