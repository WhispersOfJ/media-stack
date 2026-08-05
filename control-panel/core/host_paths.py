"""Read-only host mounts shared across Phase 4 services (diagnostics,
backups, per-app config reads) - ported from app.py's top-level constants
(app.py lines ~97-110). See docker-compose.yml's control-panel volumes for
what backs each of these.
"""
HOST_CONFIG_DIR = "/host-config"
HOST_MNT_DIR = "/mnt"
# Only present once the compose privilege change for Force Unstick lands -
# every helper that reads these degrades gracefully (empty result, not a
# 500) if the mount isn't there.
HOST_PROC_DIR = "/host-proc"
HOST_SYS_FUSE_DIR = "/host-sys-fuse"
HOST_BACKUP_LOCAL = "/host-backups/stack-restic-repo"
HOST_BACKUP_OFFSITE = "/host-backup-offsite"
HOST_RESTIC_PASSWORD_FILE = "/host-backups/.restic-password"
HOST_README = "/host-README.md"
