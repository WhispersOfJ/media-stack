function stack-mount-health --description 'Check every known FUSE mountpoint resolves cleanly'
    __stack_api GET /api/v2/host/mount-health
end
