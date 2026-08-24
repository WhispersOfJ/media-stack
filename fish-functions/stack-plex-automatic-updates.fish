function stack-plex-automatic-updates --description "Trigger Plex's own app-update check (unrelated to library media)"
    __stack_api POST /api/v2/plex/butler/automatic-updates
end
