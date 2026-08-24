function stack-plex-generate-voice-activity --description 'Generate voice-activity data (used for dialogue boost)'
    __stack_api POST /api/v2/plex/butler/generate-voice-activity
end
