#!/usr/bin/env python3
"""Safe wrapper around `docker compose` for the media-stack, with mount-cascade awareness.

Usage:
    handler.py status [service]
    handler.py restart <service> [--no-cascade]
    handler.py up [service...]
    handler.py down
    handler.py recreate <service>
    handler.py logs <service> [--tail N]
    handler.py cascade-map
"""
import argparse
import subprocess
import sys
from pathlib import Path

# Known FUSE-mount-owning services -> containers that bind-mount their output and
# must be restarted afterward or they'll keep serving a stale mount handle.
# Update this when the compose topology changes; it cannot be inferred from
# docker-compose.yml alone.
#
# CORRECTION, 2026-07-29: the comment that used to live here claimed nzbdav
# itself wasn't a cascade dependent because it's only an upstream prereq for
# nzbdav_rclone (the WebDAV source it mounts). That was wrong - nzbdav's own
# compose volumes include a direct `/mnt:/mnt` bind, so it holds a FUSE handle
# into the same mount just like radarr/sonarr/plex/unpackerr/cleanuparr do.
# Confirmed live: after nzbdav_rclone auto-remounted from an rclone vfs-cache
# error, nzbdav's own bind went "Socket not connected" and its background
# health-check/repair sweep mass-deleted 667 library bookkeeping entries
# because it couldn't tell "transient stale mount" from "file genuinely gone".
#
# nzbdav also complicates the restart order: docker-compose.yml has
# nzbdav_rclone depends_on nzbdav with `restart: true`, so `docker compose
# restart nzbdav` automatically ALSO restarts nzbdav_rclone as a side effect -
# which re-stales nzbdav's own bind again, and would re-stale any dependents
# that had already been restarted before nzbdav in the sequence. Restarting
# nzbdav via a plain `docker restart` (bypassing `docker compose`, which is
# what evaluates depends_on/restart:true) avoids triggering that side-cascade,
# so nzbdav is restarted last, after nzbdav_rclone and every other dependent
# have already settled on their final mount instance. Verified live 2026-07-29.
FUSE_MOUNT_DEPENDENTS = ["radarr", "sonarr", "plex", "unpackerr", "cleanuparr"]
CASCADE_MAP = {
    "nzbdav_rclone": FUSE_MOUNT_DEPENDENTS,
    "nzbdav": FUSE_MOUNT_DEPENDENTS,
}


def compose(compose_dir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose", *args]
    return subprocess.run(cmd, cwd=compose_dir, check=check)


def cmd_status(compose_dir: Path, service: str | None) -> None:
    args = ["ps"]
    if service:
        args.append(service)
    compose(compose_dir, *args)


def cmd_restart(compose_dir: Path, service: str, no_cascade: bool) -> None:
    targets = [service]
    dependents = CASCADE_MAP.get(service, [])
    if dependents and not no_cascade:
        print(f"[cascade] {service} shares a FUSE mount with: {', '.join(dependents)}")
        print("[cascade] restarting mount owner, then dependents, then re-binding nzbdav last")
        # Anchor on nzbdav_rclone regardless of which cascade key was passed
        # (nzbdav or nzbdav_rclone) - it's the actual FUSE mount owner, and
        # restarting it is what produces a fresh mount instance for everyone
        # else to bind to.
        compose(compose_dir, "restart", "nzbdav_rclone")
        for dep in dependents:
            compose(compose_dir, "restart", dep)
        # nzbdav itself bind-mounts /mnt too, so it needs re-binding after the
        # above like any other dependent - but `docker compose restart nzbdav`
        # would trigger nzbdav_rclone's depends_on(restart:true) and re-stale
        # everything just restarted above. A plain `docker restart` skips
        # compose's dependency evaluation entirely, so it can safely run last.
        subprocess.run(["docker", "restart", "nzbdav"], check=True)
        return
    compose(compose_dir, "restart", *targets)


def cmd_up(compose_dir: Path, services: list[str]) -> None:
    compose(compose_dir, "up", "-d", *services)


def cmd_down(compose_dir: Path) -> None:
    confirm = input(
        "This will stop the ENTIRE stack (all containers). Type 'yes' to confirm: "
    ).strip().lower()
    if confirm != "yes":
        print("Aborted.")
        return
    compose(compose_dir, "down")


def cmd_recreate(compose_dir: Path, service: str) -> None:
    # Required after editing a single-file bind mount: `up -d` alone can silently
    # keep serving the stale pre-edit file to an already-running container.
    compose(compose_dir, "up", "-d", "--force-recreate", service)


def cmd_logs(compose_dir: Path, service: str, tail: int) -> None:
    compose(compose_dir, "logs", "--tail", str(tail), service)


def cmd_cascade_map() -> None:
    for owner, deps in CASCADE_MAP.items():
        print(f"{owner} -> {', '.join(deps)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-dir", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="action", required=True)

    p_status = sub.add_parser("status")
    p_status.add_argument("service", nargs="?")

    p_restart = sub.add_parser("restart")
    p_restart.add_argument("service")
    p_restart.add_argument("--no-cascade", action="store_true")

    p_up = sub.add_parser("up")
    p_up.add_argument("service", nargs="*")

    sub.add_parser("down")

    p_recreate = sub.add_parser("recreate")
    p_recreate.add_argument("service")

    p_logs = sub.add_parser("logs")
    p_logs.add_argument("service")
    p_logs.add_argument("--tail", type=int, default=200)

    sub.add_parser("cascade-map")

    args = parser.parse_args()

    if args.action == "cascade-map":
        cmd_cascade_map()
        return 0

    compose_dir = args.compose_dir
    if not (compose_dir / "docker-compose.yml").exists():
        print(f"error: no docker-compose.yml found in {compose_dir}", file=sys.stderr)
        return 1

    if args.action == "status":
        cmd_status(compose_dir, args.service)
    elif args.action == "restart":
        cmd_restart(compose_dir, args.service, args.no_cascade)
    elif args.action == "up":
        cmd_up(compose_dir, args.service)
    elif args.action == "down":
        cmd_down(compose_dir)
    elif args.action == "recreate":
        cmd_recreate(compose_dir, args.service)
    elif args.action == "logs":
        cmd_logs(compose_dir, args.service, args.tail)

    return 0


if __name__ == "__main__":
    sys.exit(main())
