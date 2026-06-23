"""Tests for GET /api/llm/settings — read-only, masked API keys."""
from app.config import settings as settings_module


def test_llm_settings_returns_basic_shape(client):
    r = client.get("/api/llm/settings")
    assert r.status_code == 200
    data = r.json()
    assert "provider" in data
    for key in ("anthropic", "openai", "embedding", "retrieval"):
        assert key in data, f"missing section: {key}"
    for prov in ("anthropic", "openai"):
        assert {"api_key", "base_url", "model"}.issubset(data[prov].keys())
    assert {"model", "dimensions"}.issubset(data["embedding"].keys())
    assert {"top_k", "threshold"}.issubset(data["retrieval"].keys())


def test_llm_settings_masks_api_keys(client, monkeypatch):
    # Set known long keys so masking logic is exercised end-to-end.
    monkeypatch.setattr(settings_module, "anthropic_api_key", "sk-abcdefghij-12345")
    monkeypatch.setattr(settings_module, "openai_api_key", "sk-zyxwvutsrq-98765")
    monkeypatch.setattr(settings_module, "llm_provider", "claude")

    r = client.get("/api/llm/settings")
    assert r.status_code == 200
    data = r.json()

    a = data["anthropic"]["api_key"]
    o = data["openai"]["api_key"]
    assert a == "sk-a***2345"
    assert o == "sk-z***8765"
    # Make sure raw keys never leak
    assert "abcdefghij" not in a
    assert "zyxwvutsrq" not in o


def test_llm_settings_empty_key_shows_blank(client, monkeypatch):
    monkeypatch.setattr(settings_module, "anthropic_api_key", "")
    r = client.get("/api/llm/settings")
    assert r.status_code == 200
    assert r.json()["anthropic"]["api_key"] == ""


def test_llm_settings_short_key_fully_masked(client, monkeypatch):
    monkeypatch.setattr(settings_module, "openai_api_key", "abc")
    r = client.get("/api/llm/settings")
    assert r.json()["openai"]["api_key"] == "***"
