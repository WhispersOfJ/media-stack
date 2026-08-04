"""Evolved control-panel backend entrypoint - Phase 1 of
.claude/plans/evolved-control-panel-backend.plan.md. Runs ALONGSIDE the
existing app.py during the phased migration; docker-compose.yml's CMD
still points at app:app until Phase 5's cutover, so this module has zero
effect on the live container until that switch happens.
"""
import importlib
import os
from pathlib import Path

from fastapi import FastAPI

import models  # noqa: F401  (registers every table on Base before create_all)
from core.db import Base, SessionLocal, engine
from core.security import hash_api_key, hash_password
from models.api_key import ApiKey
from models.user import User

app = FastAPI(title="Control Panel (evolved backend)")


def _bootstrap_admin(db) -> None:
    """Creates the single admin account on first boot only - matches the
    plan's single-operator auth model. No-op if any user already exists,
    or if the env vars aren't set (e.g. during tests)."""
    username = os.environ.get("CONTROL_PANEL_ADMIN_USERNAME")
    password = os.environ.get("CONTROL_PANEL_ADMIN_PASSWORD")
    if not username or not password:
        return
    if db.query(User).count() > 0:
        return
    db.add(User(username=username, password_hash=hash_password(password), is_admin=True))
    db.commit()


def _bootstrap_service_key(db) -> None:
    """Upserts the health-check-loop's service API key by name, so
    rotating CONTROL_PANEL_SERVICE_API_KEY and recreating the container
    replaces the old hash instead of accumulating stale rows."""
    raw_key = os.environ.get("CONTROL_PANEL_SERVICE_API_KEY")
    if not raw_key:
        return
    key_hash = hash_api_key(raw_key)
    existing = db.query(ApiKey).filter(ApiKey.name == "healthcheck-cron").first()
    if existing is not None:
        existing.key_hash = key_hash
    else:
        db.add(ApiKey(name="healthcheck-cron", key_hash=key_hash))
    db.commit()


def _startup() -> None:
    """Runs at import time, not as an ASGI startup hook - app.py already
    does its own setup (docker.from_env(), ARR_APPS) at import time (see
    tests/conftest.py's cp_app fixture comments), and this avoids a real
    footgun: FastAPI's on_event/lifespan hooks only fire for a TestClient
    used as a context manager, which silently skipped table creation the
    first time this was written as an on_event hook."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _bootstrap_admin(db)
        _bootstrap_service_key(db)
    finally:
        db.close()


_startup()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


SERVICES_DIR = Path(__file__).parent / "services"


def _discover_routers() -> None:
    """Mounts every services/<name>/router.py's `router` - adding a new
    integration means adding a new directory, not editing this file."""
    for entry in sorted(SERVICES_DIR.iterdir()):
        if not entry.is_dir() or not (entry / "router.py").is_file():
            continue
        module = importlib.import_module(f"services.{entry.name}.router")
        router = getattr(module, "router", None)
        if router is not None:
            app.include_router(router)


_discover_routers()
