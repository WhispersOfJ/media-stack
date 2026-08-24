function stack-plex-generate-media-index --description 'Generate media index files used for fast seeking'
    __stack_api POST /api/v2/plex/butler/generate-media-index
end
