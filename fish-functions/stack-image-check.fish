function stack-image-check --description 'Check digest/exact-version-pinned images for a newer registry digest'
    __stack_api GET /api/v2/host/image-check
end
