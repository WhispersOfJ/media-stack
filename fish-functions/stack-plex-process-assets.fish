function stack-plex-process-assets --description 'Process pending local assets (posters, themes, etc)'
    __stack_api POST /api/v2/plex/butler/process-assets
end
