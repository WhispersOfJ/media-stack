# Usage: stack-newapps-backup-check
# Verifies each of the 8 new apps' config dir appears in the latest local
# restic snapshot, rather than just trusting that ./config is backed up whole.
function stack-newapps-backup-check --description 'Verify all 8 new apps are in the latest backup snapshot'
    __stack_api GET /api/newapps/backup-check
end
