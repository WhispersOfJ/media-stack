function stack-plex-loudness-analysis --description 'Analyze audio loudness for volume leveling'
    __stack_api POST /api/v2/plex/butler/loudness-analysis
end
