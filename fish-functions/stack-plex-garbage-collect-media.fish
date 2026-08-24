function stack-plex-garbage-collect-media --description 'Garbage-collect unused library media records'
    __stack_api POST /api/v2/plex/butler/garbage-collect-media
end
