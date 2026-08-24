function stack-plex-refresh-libraries --description 'Refresh metadata for every library'
    __stack_api POST /api/v2/plex/butler/refresh-libraries
end
