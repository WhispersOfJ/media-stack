function stack-plex-backup-database --description "Back up Plex's database to its configured backup directory"
    __stack_api POST /api/v2/plex/butler/backup-database
end
