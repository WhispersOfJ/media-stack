"""Direct unit tests of verify_same_origin() (app.py:230) - the CSRF
hardening that stands in for auth on this LAN-only, no-login panel (see
app.py's own comment above ALLOWED_HOSTS). Called directly with a stub
request/call_next rather than through TestClient, so these stay pure
logic tests with no HTTP/ASGI machinery involved.
"""
import asyncio
from types import SimpleNamespace

import pytest

SENTINEL = object()


async def _call_next(request):
    return SENTINEL


def _run(cp_app, method, headers, client_host="127.0.0.1"):
    request = SimpleNamespace(
        method=method,
        headers=headers,
        client=SimpleNamespace(host=client_host) if client_host is not None else None,
    )
    return asyncio.run(cp_app.verify_same_origin(request, _call_next))


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_methods_bypass_the_check_entirely(cp_app, method):
    result = _run(cp_app, method, {"host": "totally-untrusted.example.com"})
    assert result is SENTINEL


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutating_methods_are_checked(cp_app, method):
    result = _run(cp_app, method, {"host": "totally-untrusted.example.com"})
    assert result is not SENTINEL
    assert result.status_code == 403


def test_allows_localhost_host_with_no_origin(cp_app):
    result = _run(cp_app, "POST", {"host": "localhost:8420"})
    assert result is SENTINEL


def test_allows_127_0_0_1_host(cp_app):
    result = _run(cp_app, "POST", {"host": "127.0.0.1:8420"})
    assert result is SENTINEL


def test_rejects_unknown_host(cp_app):
    result = _run(cp_app, "POST", {"host": "evil.example.com"})
    assert result.status_code == 403
    assert "Host header" in result.body.decode()


def test_rejects_mismatched_origin_even_with_good_host(cp_app):
    result = _run(cp_app, "POST", {"host": "localhost", "origin": "http://evil.example.com"})
    assert result.status_code == 403
    assert "Origin" in result.body.decode()


def test_allows_matching_origin(cp_app):
    result = _run(cp_app, "POST", {"host": "localhost:8420", "origin": "http://localhost:8420"})
    assert result is SENTINEL


def test_no_origin_header_is_not_required(cp_app):
    # Non-browser clients (curl, the stack-* CLI) never send Origin at all -
    # only Host is checked when Origin is absent.
    result = _run(cp_app, "DELETE", {"host": "127.0.0.1"})
    assert result is SENTINEL


def test_rejects_spoofed_localhost_host_from_non_loopback_client(cp_app):
    # The exact attack this check exists to stop: `curl -H "Host: localhost"
    # http://<real-host-ip>:8420/...` from a real remote client. The Host
    # header alone can't be trusted - only the actual TCP source can.
    result = _run(cp_app, "POST", {"host": "localhost:8420"}, client_host="203.0.113.5")
    assert result.status_code == 403
    assert "wasn't actually local" in result.body.decode()


def test_missing_client_on_localhost_host_is_rejected(cp_app):
    # ASGI servers may report request.client as None (e.g. behind certain
    # proxies/test harnesses) - that must fail closed, not open.
    result = _run(cp_app, "POST", {"host": "localhost:8420"}, client_host=None)
    assert result.status_code == 403
    assert "wasn't actually local" in result.body.decode()
