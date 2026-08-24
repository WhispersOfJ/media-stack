function stack-plex-generate-credits-markers --description 'Generate end-credits markers for eligible media'
    __stack_api POST /api/v2/plex/butler/generate-credits-markers
end
