"""PlexAniSync routes - Phase 7 of PLANS.md's 7-service integration batch.

PlexAniSync pushes anime watch state from Plex to AniList. Unlike every other
service in this batch it has no API, no port and no persistent process: it is a
container that runs once and exits, fired by systemd/plexanisync.timer. So
these routes read the container's own exit state and logs instead of proxying
anything.

Four things that shape this module:

1. **The container is re-started, not re-created.** docker-compose.yml keeps it
   behind the "scheduled" profile with INTERVAL=0 (sync once, exit). Both
   triggers - the timer and /run-now here - start that same container, so its
   logs survive between runs and /last-run has something to read. A
   `compose run --rm` design would leave this route with nothing to parse.

2. **Exit code 0 is not sufficient for success.** PlexAniSync exits 0 after a
   run in which every title failed to match, so /last-run reports the parsed
   counts alongside the exit code rather than in place of it.

3. **An expired AniList token is the expected failure**, not an exotic one - it
   is a 1-year OAuth token with no non-interactive renewal (see .env.example
   and STACK.md). Its signature in the logs gets named explicitly so the answer
   is "renew the token", not "read 2000 log lines".

4. **No health dot.** SERVICE_META carries health_check=None like kometa's:
   this container is *supposed* to be sitting in Exited(0) between runs, and a
   fleet tile that renders that as "down" would be wrong four times a day.
"""
import re
from datetime import datetime, timezone

import docker
from core.docker_client import docker_client
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(tags=["plexanisync"])

SERVICE_META = {"label": "PlexAniSync", "health_check": None}

CONTAINER = "plexanisync"
# Enough to cover one full run's output without pulling the whole retained log.
LOG_TAIL = 3000

# PlexAniSync emits no end-of-run summary at all - it logs per title and then
# prints one "sync finished" line. So these count occurrences rather than read
# a total, and the strings are upstream's exact ones (plexanisync/anilist.py
# and plexanisync/plexmodule.py), not a paraphrase:
#
#   plexmodule.py:275  "Found {n} watched series"
#   anilist.py:506     "Found AniList entry for Plex title: {title}"
#   anilist.py:411,442 "No match found for title: {title}"
#
# Only "watched" is a stated number; the other two are tallies of per-title
# lines. Counting is what makes "ran fine, matched nothing" visible, which an
# exit code alone cannot say.
_TOTAL_PATTERNS = {
    "watched": re.compile(r"Found (\d+) watched series"),
}
_TALLY_PATTERNS = {
    "matched": re.compile(r"Found AniList entry for Plex title:"),
    "unmatched": re.compile(r"No match found for title:"),
}
# The end-of-run marker (PlexAniSync.py). Its absence in a stopped container
# means the run died partway rather than completing.
_FINISHED = re.compile(r"Plex to AniList sync finished")
# An expired AniList token surfaces as an auth failure from AniList's GraphQL
# endpoint, not as a distinct exit code - see the module docstring.
_TOKEN_EXPIRED = re.compile(r"(?i)(invalid token|unauthorized|401)")


class RunRequest(BaseModel):
    pass


def _container():
    try:
        return docker_client.containers.get(CONTAINER)
    except docker.errors.NotFound:
        fail(f"Container '{CONTAINER}' does not exist yet - it is created by "
             f"`docker compose --profile scheduled up --no-start {CONTAINER}` "
             f"(systemd/plexanisync.service does this itself on each run).")


def _parse_timestamp(value: str | None) -> str | None:
    """Docker returns RFC3339 with nanoseconds and a zero value for 'never'."""
    if not value or value.startswith("0001-01-01"):
        return None
    cleaned = re.sub(r"(\.\d{6})\d+", r"\1", value.replace("Z", "+00:00"))
    try:
        return datetime.fromisoformat(cleaned).astimezone().isoformat(timespec="seconds")
    except ValueError:
        return value


def _age_seconds(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - parsed).total_seconds())


def _logs(container, tail: int = LOG_TAIL) -> str:
    return container.logs(tail=tail).decode(errors="replace")


def _counts(raw: str) -> dict:
    """What the last run actually did, from its per-title log lines.

    Stated totals and tallies are kept apart on purpose. A stated total that
    did not parse is `None` - "unknown", never 0, because 0 watched series is a
    real and alarming answer that must not be manufactured by a log-format
    change. A tally of 0 is trustworthy in the same situation only because it
    is counted from lines that are either there or not.
    """
    counts = {}
    for key, pattern in _TOTAL_PATTERNS.items():
        found = pattern.findall(raw)
        counts[key] = int(found[-1]) if found else None
    for key, pattern in _TALLY_PATTERNS.items():
        counts[key] = len(pattern.findall(raw))
    return counts


@router.get("/api/plexanisync/last-run")
def plexanisync_last_run(_=Depends(current_user_or_service)):
    """Outcome of the most recent sync: when it ran, how it exited, what it
    matched, and whether the AniList token looks expired.

    There is no REST API to ask - PlexAniSync is a batch container - so this is
    the container's own State plus a parse of its retained logs.
    """
    container = _container()
    state = (container.attrs or {}).get("State", {})
    started = _parse_timestamp(state.get("StartedAt"))
    finished = _parse_timestamp(state.get("FinishedAt"))
    running = state.get("Running", False)
    exit_code = state.get("ExitCode")

    raw = _logs(container)
    counts = _counts(raw)
    token_expired = bool(_TOKEN_EXPIRED.search(raw)) and not running and exit_code not in (0, None)
    completed = bool(_FINISHED.search(raw))

    if running:
        message = f"A sync is running now (started {started})."
    elif not started:
        message = "Never run. Trigger one with stack-plexanisync-run-now, or wait for the timer."
    elif token_expired:
        message = (f"Last run FAILED at {finished} and the logs look like an expired "
                   f"AniList token - renew it (see STACK.md's PlexAniSync entry) and "
                   f"update PLEXANISYNC_ANILIST_TOKEN in .env.")
    elif exit_code == 0 and completed:
        watched = counts["watched"]
        seen = "unknown" if watched is None else watched
        message = (f"Last run succeeded at {finished}: {seen} watched series in Plex, "
                   f"{counts['matched']} matched on AniList, {counts['unmatched']} unmatched.")
    elif exit_code == 0:
        # Exit 0 without the end-of-run line: the process stopped early - a
        # killed container, or an INTERVAL misconfiguration that made it exit
        # before syncing. Not a success.
        message = (f"Last run exited 0 at {finished} but never logged 'sync finished' - "
                   f"it stopped partway. See the log tail.")
    else:
        message = f"Last run FAILED at {finished} (exit {exit_code}) - see the log tail."

    return ok(
        message,
        running=running,
        exit_code=exit_code,
        completed=completed,
        started_at=started,
        finished_at=finished,
        age_seconds=_age_seconds(finished or started),
        counts=counts,
        token_expired=token_expired,
        log_tail=raw[-2000:],
    )


@router.post("/api/plexanisync/run-now")
def plexanisync_run_now(_payload: RunRequest | None = None, _=Depends(current_user_or_service)):
    """Start an out-of-schedule sync.

    Detached: a full run walks both anime libraries and rate-limits against
    AniList, which takes minutes. The result shows up in
    /api/plexanisync/last-run, not here. Starting a second run while one is
    already going is refused rather than queued - Docker cannot start an
    already-running container, and two concurrent runs would push conflicting
    updates to the same AniList list.
    """
    container = _container()
    container.reload()
    if (container.attrs or {}).get("State", {}).get("Running"):
        fail("A PlexAniSync run is already in progress - check "
             "stack-plexanisync-last-run.", status_code=409)
    try:
        container.start()
    except docker.errors.APIError as e:
        fail(f"Couldn't start '{CONTAINER}': {e}")
    return ok("PlexAniSync sync started in the background - it takes minutes. "
              "Check stack-plexanisync-last-run for the result.")


@router.get("/api/plexanisync/logs")
def plexanisync_logs(lines: int = 200, _=Depends(current_user_or_service)):
    """Tails the container's own log output (stdout only, no log file)."""
    if lines <= 0:
        fail("lines must be a positive integer.", status_code=400)
    container = _container()
    return ok(f"Last {lines} line(s) from {CONTAINER}.", log=_logs(container, min(lines, 5000)))
