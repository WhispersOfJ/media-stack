function stack-plex-refresh-local-media --description 'Refresh local media file changes'
    __stack_api POST /api/v2/plex/butler/refresh-local-media
end
