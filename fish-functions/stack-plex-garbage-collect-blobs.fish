function stack-plex-garbage-collect-blobs --description 'Garbage-collect unused metadata blobs'
    __stack_api POST /api/v2/plex/butler/garbage-collect-blobs
end
