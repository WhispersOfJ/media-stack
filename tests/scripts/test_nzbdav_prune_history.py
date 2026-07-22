import urllib.error


def test_delete_one_success(nzbdav_prune_history, monkeypatch):
    monkeypatch.setattr(nzbdav_prune_history, "api_get", lambda params, timeout=30: {"status": True})
    ok, message = nzbdav_prune_history.delete_one({"nzo_id": "abc", "name": "Some Release"})
    assert ok is True
    assert message is None


def test_delete_one_rejected_by_server(nzbdav_prune_history, monkeypatch):
    monkeypatch.setattr(
        nzbdav_prune_history, "api_get",
        lambda params, timeout=30: {"status": False, "error": "not found"},
    )
    ok, message = nzbdav_prune_history.delete_one({"nzo_id": "abc", "name": "Some Release"})
    assert ok is False
    assert "delete rejected" in message
    assert "not found" in message


def test_delete_one_network_failure(nzbdav_prune_history, monkeypatch):
    def _raise(params, timeout=30):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(nzbdav_prune_history, "api_get", _raise)
    ok, message = nzbdav_prune_history.delete_one({"nzo_id": "abc", "name": "Some Release"})
    assert ok is False
    assert "failed to delete abc" in message


def test_delete_one_passes_expected_params(nzbdav_prune_history, monkeypatch):
    captured = {}

    def _api_get(params, timeout=30):
        captured.update(params)
        return {"status": True}

    monkeypatch.setattr(nzbdav_prune_history, "api_get", _api_get)
    nzbdav_prune_history.delete_one({"nzo_id": "xyz", "name": "Foo"})
    assert captured["mode"] == "history"
    assert captured["name"] == "delete"
    assert captured["value"] == "xyz"
    assert captured["output"] == "json"
