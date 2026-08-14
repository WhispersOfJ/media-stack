"""Every fish command that takes an Arr app must reach all four instances.

radarr-anime and sonarr-anime ran for eight days behind an 18-function wall
of `contains -- $argv[1] radarr sonarr` guards. Fixing those by hand fixes
today; this file is what stops the fifth instance from repeating it, by
failing the moment a command advertises an app argument and accepts only
two values.
"""
import re
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent / "fish-functions"

# The normalizer every app-taking command routes through.
HELPER = "__stack_arr_app"

# Commands that name an Arr app but deliberately do not take one as a
# positional argument. Each needs a reason, not just an entry.
EXEMPT = {
    # Fleet-wide: no app argument at all, the router iterates ARR_APPS and
    # already returns all four instances.
    "stack-arr-import-backlog", "stack-arr-queue-errors", "stack-queue-status",
    "stack-backlog-status", "stack-arr-import-starvation", "stack-queue-autofix",
    "stack-command-queue-summary",
    # Selects its instance with --anime, matching the Letterboxd/MDBList
    # family, because only one of the two shapes is ever valid.
    "stack-loop-exclude", "stack-sonarr-fix-episode-monitoring",
    # Takes a container name, not an ARR_APPS key - covered by its own test
    # below because prowlarr is valid there and the spellings differ.
    "stack-arr-logs",
}

ALL_INSTANCES = {"radarr", "sonarr", "radarr_anime", "sonarr_anime"}


def _commands():
    return sorted(REPO_DIR.glob("stack-*.fish"))


def _usage_line(text, command):
    m = re.search(rf"^#\s*Usage:\s*{re.escape(command)}\s*(.*)$", text, re.M)
    return m.group(1) if m else ""


def _app_arg_commands():
    """Commands whose first positional is an Arr app, by their own usage."""
    out = []
    for path in _commands():
        if path.stem in EXEMPT:
            continue
        text = path.read_text()
        usage = _usage_line(text, path.stem)
        first = re.match(r"\s*<([^>]+)>", usage)
        if first and "radarr" in first.group(1) and "|" in first.group(1):
            out.append((path.stem, path, text, first.group(1)))
    return out


def test_the_audit_found_the_commands_it_should():
    """A guard on the guard: if this drops to a handful, the parser broke
    and every test below is passing vacuously."""
    assert len(_app_arg_commands()) >= 15


@pytest.mark.parametrize("name,path,text,arg", _app_arg_commands(),
                         ids=[c[0] for c in _app_arg_commands()])
def test_app_argument_advertises_all_four_instances(name, path, text, arg):
    offered = {v.strip() for v in arg.split("|")}
    missing = ALL_INSTANCES - offered
    assert not missing, f"{name} usage offers {sorted(offered)}, missing {sorted(missing)}"


@pytest.mark.parametrize("name,path,text,arg", _app_arg_commands(),
                         ids=[c[0] for c in _app_arg_commands()])
def test_app_argument_is_validated_through_the_helper(name, path, text, arg):
    """Accepting the name in the usage string but rejecting it at runtime is
    worse than not offering it - the command documents a lie."""
    assert HELPER in text, f"{name} takes an app argument but never calls {HELPER}"


@pytest.mark.parametrize("name,path,text,arg", _app_arg_commands(),
                         ids=[c[0] for c in _app_arg_commands()])
def test_no_hardcoded_two_app_guard_survives(name, path, text, arg):
    assert "contains -- $argv[1] radarr sonarr" not in text, (
        f"{name} still carries the hardcoded two-app guard")


def test_helper_exists_and_covers_every_instance():
    helper = (REPO_DIR / f"{HELPER}.fish").read_text()
    for instance in ALL_INSTANCES:
        assert instance in helper, f"{HELPER} does not know {instance}"
    # Both spellings, because Docker and the API disagree and both are real.
    assert "radarr-anime" in helper
    assert "--container" in helper or "_flag_container" in helper


def test_logs_command_uses_container_spellings():
    """The one command that takes container names: hyphens, plus prowlarr,
    which is not an ARR_APPS key at all."""
    text = (REPO_DIR / "stack-arr-logs.fish").read_text()
    usage = _usage_line(text, "stack-arr-logs")
    for expected in ("radarr-anime", "sonarr-anime", "prowlarr"):
        assert expected in usage, f"stack-arr-logs usage is missing {expected}"
    assert "--container" in text


def test_toggle_search_all_covers_every_instance():
    """`all` meaning two of four is the costliest silent failure here: you
    believe grabbing is paused while the anime instances keep grabbing."""
    text = (REPO_DIR / "stack-arr-toggle-search.fish").read_text()
    m = re.search(r"set apps ([a-z_ ]+)\n", text)
    assert m, "could not find the `all` expansion"
    assert set(m.group(1).split()) == ALL_INSTANCES


def test_customformat_cache_is_keyed_on_the_normalized_name():
    """Keyed on raw input, `radarr-anime` and `radarr_anime` keep rival
    caches and every diff after a spelling change reads as a total rewrite."""
    text = (REPO_DIR / "stack-customformat-diff.fish").read_text()
    assert "customformat-$app.json" in text
    assert "customformat-$argv[1].json" not in text
