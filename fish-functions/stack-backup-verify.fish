function stack-backup-verify --description 'Check both local and off-site restic repos have a recent snapshot'
    __stack_api GET /api/backup-verify
end
