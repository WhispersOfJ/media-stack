function stack-plex-clean-log-files --description 'Delete old supplemental Plex log files'
    __stack_api POST /api/v2/plex/butler/clean-log-files
end
