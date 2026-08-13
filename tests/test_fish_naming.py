"""Phase 8b: the naming schema for this stack's fish commands, as a gate test.

This file is the schema. There is no prose document that can drift from it -
if a rule is not encoded here, it is not a rule, and the failure output of
these tests is the audit PLANS.md 8.4 asked for.

Two domain namespaces exist and both are legitimate: service commands, whose
domain is a container in docker-compose.yml, and host commands (disk, journal,
kernel, pkg...), which are not services at all. Conflating them was the real
inconsistency behind 66 distinct domain tokens across 190 functions.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_DIR = REPO_ROOT / "fish-functions"
COMPOSE = REPO_ROOT / "docker-compose.yml"

# Host-level concerns. Not services, deliberately not renamed - see the spec's
# decision 5. Adding a domain here is how a new host command becomes legal.
HOST_DOMAINS = {
    "aur", "backlog", "claude", "command", "container", "cron", "disk",
    "docker", "firewall", "flatpak", "git", "image", "journal", "kernel",
    "log", "loop", "mem", "mount", "newapps", "notify", "oom", "perms",
    "pkg", "queue", "reboot", "resource", "restart", "service", "ssh",
    "status", "timer", "top", "uptime", "version", "zombie",
}
# `loop` joined the list in Phase 8b: stack-loop-{candidates,unmonitor,exclude}
# read the queue-autofix history across both Arr apps and take the app as an
# argument, so the loop is the domain, not radarr or sonarr. Same shape as
# `queue` and `backlog`, which were already here.

# Named after the data source rather than the target app, kept as a documented
# exception - they read as intent and tab-complete by source. Spec decision 3.
SOURCE_FIRST_DOMAINS = {"imdb", "letterboxd", "mdblist", "tmdb", "trakt"}

# Bare names with no action, allowlisted as top-level entry points. Renaming
# the most-typed command in the stack for schema purity costs more than it
# returns. Two shapes are allowed here and neither is an inconsistency:
#
#   dispatchers - the action is an argument, not part of the name, so the name
#   is a domain by design: stack-arr <app> <action>, stack-plex <action>,
#   stack-container <name> <action>.
#
#   bare reads - a noun that names what it prints, with no action to state:
#   stack-status, stack-top, stack-version, stack-help.
TOP_LEVEL_COMMANDS = {
    "stack-arr", "stack-container", "stack-help", "stack-plex",
    "stack-status", "stack-top", "stack-version",
}

# Domains that are real but whose container name does not match the token
# (e.g. the arr family is addressed as one domain with an app argument).
EXTRA_SERVICE_DOMAINS = {"arr", "customformat", "cutoff", "rating", "recently", "import"}


def _compose_services() -> set[str]:
    """Service names from docker-compose.yml, without parsing YAML - the file
    has anchors and merge keys that a naive loader chokes on, and this only
    needs the top-level keys under `services:`."""
    domains = set()
    in_services = False
    for line in COMPOSE.read_text().splitlines():
        if line.startswith("services:"):
            in_services = True
            continue
        if in_services and line and not line[0].isspace():
            break
        match = re.match(r"^  ([a-z0-9][a-z0-9_-]*):\s*$", line)
        if in_services and match:
            name = match.group(1)
            domains.add(name)
            # radarr-anime is reached as `stack-radarr-*` with an argument.
            domains.add(name.split("-")[0])
    return domains


SERVICE_DOMAINS = _compose_services() | EXTRA_SERVICE_DOMAINS


def _functions() -> list[tuple[str, Path]]:
    return [(path.stem, path) for path in sorted(REPO_DIR.glob("stack-*.fish"))]


def test_filename_matches_the_declared_function_name():
    """A mismatch means `stack-foo` runs code from stack-bar.fish - fish
    autoloads by filename, so the file wins and the declaration is a lie."""
    offenders = []
    for name, path in _functions():
        declared = re.search(r"^function\s+(\S+)", path.read_text(), re.MULTILINE)
        if not declared:
            offenders.append(f"{name}: no `function` declaration")
        elif declared.group(1) != name:
            offenders.append(f"{name}: declares `{declared.group(1)}`")
    assert not offenders, "\n  " + "\n  ".join(offenders)


def test_every_domain_is_known():
    """An unknown domain is usually a typo or an invented namespace. Adding a
    legitimate one means adding it to HOST_DOMAINS or a compose service."""
    known = SERVICE_DOMAINS | HOST_DOMAINS | SOURCE_FIRST_DOMAINS
    offenders = [name for name, _ in _functions()
                 if name not in TOP_LEVEL_COMMANDS and name.split("-")[1] not in known]
    assert not offenders, (
        "unknown domain in:\n  " + "\n  ".join(sorted(offenders)))


def test_no_bare_domain_names_outside_the_allowlist():
    """`stack-container` with no action is ambiguous; it is allowlisted only
    because it predates the schema and is typed constantly."""
    offenders = [name for name, _ in _functions()
                 if len(name.split("-")) == 2 and name not in TOP_LEVEL_COMMANDS]
    assert not offenders, "\n  " + "\n  ".join(sorted(offenders))
