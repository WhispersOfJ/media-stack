"""Shared fixtures for the media-stack unit test suite.

control-panel/app.py runs `docker.from_env()` at import time (app.py:219),
which reaches for a real Docker socket - not available in a plain CI
runner or a throwaway venv. The `cp_app` fixture patches that out before
importing, so tests never need a live daemon.

Every test gets a *fresh* import of app.py: the module also rewires
`httpx.request`/`httpx._api.request` at import time (its API-hit-counter
hook) - reusing one cached import across tests would stack that wrapper
deeper on every test that imports it, so the fixture restores the
pre-import versions on teardown instead of leaving them patched.
"""
import importlib
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROL_PANEL_DIR = REPO_ROOT / "control-panel"
SCRIPTS_DIR = REPO_ROOT / "scripts"


@pytest.fixture
def cp_app(monkeypatch):
    monkeypatch.setattr("docker.from_env", lambda: MagicMock())
    # app.py:129/137 index these directly (os.environ[...], not .get) to
    # build ARR_APPS at import time - a real deployment always has them via
    # .env, but a test import needs stand-ins or import itself KeyErrors.
    monkeypatch.setenv("RADARR_API_KEY", "test-radarr-key")
    monkeypatch.setenv("SONARR_API_KEY", "test-sonarr-key")
    original_request = httpx.request
    original_api_request = httpx._api.request

    sys.path.insert(0, str(CONTROL_PANEL_DIR))
    sys.modules.pop("app", None)
    # app.py's own final line mounts StaticFiles(directory="static", ...) -
    # a relative path resolved against cwd, and this starlette version
    # verifies the directory exists at construction time.
    original_cwd = os.getcwd()
    os.chdir(CONTROL_PANEL_DIR)
    try:
        module = importlib.import_module("app")
        yield module
    finally:
        os.chdir(original_cwd)
        sys.modules.pop("app", None)
        sys.path.remove(str(CONTROL_PANEL_DIR))
        httpx.request = original_request
        httpx._api.request = original_api_request


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
