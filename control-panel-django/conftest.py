import os
from copy import copy

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from core.models import ApiKey, User
from core.security import hash_api_key

# core.arr_client reads these via bare os.environ[...] at import time (mirrors
# the FastAPI-era app.py: a missing key is a deployment misconfiguration that
# should fail loudly in production). Tests need *some* value present so the
# module is importable; set defaults here, before any test module imports
# core.arr_client, without clobbering a real value if one is already set.
os.environ.setdefault("RADARR_API_KEY", "test-radarr-key")
os.environ.setdefault("SONARR_API_KEY", "test-sonarr-key")
os.environ.setdefault("PROWLARR_API_KEY", "test-prowlarr-key")
os.environ.setdefault("WS_API_KEY", "test-watchstate-key")
os.environ.setdefault("MDBLIST_KEY", "test-mdblist-key")


@pytest.fixture
def authed_client(db):
    user = User.objects.create(username="bear", password_hash="x")
    client = APIClient()
    session = client.session
    session["user_id"] = user.id
    session.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
    return client


@pytest.fixture(autouse=True)
def _fix_template_context_copy():
    """Django 5.1.x + Python 3.14: BaseContext.__copy__ calls
    super().__copy__() which hits object.__copy__ and fails because
    Python 3.14 no longer auto-creates `__dict__`. Monkey-patch it
    so all template-rendering tests (including the ones that already
    exist in the project) don't raise AttributeError on context copy."""
    from django.template.context import BaseContext

    _original_copy = BaseContext.__copy__

    def _fixed_copy(self):
        # Python 3.14's object.__copy__ returns self (no-attribute-error),
        # but we need a new object. Create one then copy attrs manually.
        new = object.__new__(BaseContext)
        if hasattr(self, 'dicts'):
            new.dicts = self.dicts[:]
        if hasattr(self, 'render_context'):
            new.render_context = copy(self.render_context)
        return new

    BaseContext.__copy__ = _fixed_copy
    yield
    BaseContext.__copy__ = _original_copy


@pytest.fixture
def service_client(db):
    ApiKey.objects.create(name="test-service", key_hash=hash_api_key("test-service-key"))
    client = APIClient()
    client.credentials(HTTP_X_API_KEY="test-service-key")
    return client
