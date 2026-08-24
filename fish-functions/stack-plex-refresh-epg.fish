function stack-plex-refresh-epg --description 'Refresh Live TV/DVR EPG guide data'
    __stack_api POST /api/v2/plex/butler/refresh-epg
end
