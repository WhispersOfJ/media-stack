function stack-plex-music-analysis --description 'Analyze music library audio'
    __stack_api POST /api/v2/plex/butler/music-analysis
end
