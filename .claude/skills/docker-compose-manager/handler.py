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
# docker-compose.yml alone. altmount is the only mount owner left as of
# 2026-07-23 (replaced NzbDAV/nzbdav-rclone entirely - see CLAUDE.md's
# History) - matches control-panel/app.py's own MOUNT_PROVIDERS/
# MOUNT_DEPENDENTS sets exactly.
CASCADE_MAP = {
    "altmount": ["radarr", "sonarr", "plex", "unpackerr", "cleanuparr"],
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
        print(f"[cascade] {service} owns a FUSE mount consumed by: {', '.join(dependents)}")
        print("[cascade] restarting owner first, then dependents in order")
        compose(compose_dir, "restart", service)
        for dep in dependents:
            compose(compose_dir, "restart", dep)
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
