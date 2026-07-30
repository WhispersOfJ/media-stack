function stack-backup-restore-test --description 'Restore one file from the latest local snapshot to confirm restores actually work'
    __stack_api POST /api/backup-restore-test
end
