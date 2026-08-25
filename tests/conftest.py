"""Shared fixtures for the media-stack unit test suite (scripts/ and
systemd/fish checks)."""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _import_script(name: str):
    """Import scripts/<name>.py by file path under a private module-cache
    key. Needed because names like `arr-app-backup` aren't valid Python
    module names, so a plain `import` can't reach them even with the
    scripts dir on sys.path."""
    path = SCRIPTS_DIR / f"{name}.py"
    mod_name = f"_script_{name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


# One module-scoped fixture per tested script - each imports once per test
# module and hands back the live module object, so tests can call its
# functions directly and monkeypatch its globals.
@pytest.fixture(scope="module")
def setup_wizard():
    return _import_script("setup_wizard")


@pytest.fixture(scope="module")
def scrape_letterboxd():
    return _import_script("scrape_letterboxd")


@pytest.fixture(scope="module")
def audit_tmdb_links():
    return _import_script("audit-tmdb-links")


@pytest.fixture(scope="module")
def arr_app_backup():
    return _import_script("arr-app-backup")


@pytest.fixture(scope="module")
def enable_recycle_bin():
    return _import_script("enable-recycle-bin")


@pytest.fixture(scope="module")
def bearmount_prune_history():
    return _import_script("bearmount-prune-history")


@pytest.fixture(scope="module")
def plex_health_monitor():
    return _import_script("plex-health-monitor")


@pytest.fixture(scope="module")
def plex_webhook_listener():
    return _import_script("plex-webhook-listener")


@pytest.fixture(scope="module")
def plex_library_report():
    return _import_script("plex-library-report")


@pytest.fixture(scope="module")
def poster_sync_fanart():
    return _import_script("poster-sync-fanart")


@pytest.fixture(scope="module")
def watchstate_provision():
    return _import_script("watchstate-provision")


@pytest.fixture(scope="module")
def mdblist_toplists_import():
    return _import_script("mdblist_toplists_import")


@pytest.fixture(scope="module")
def provision_cleanuparr_instances():
    return _import_script("provision-cleanuparr-instances")
