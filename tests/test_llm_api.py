from unittest.mock import MagicMock

from app.llm.base import LLMResponse


def test_llm_ping_returns_text(client, monkeypatch):
    fake_resp = LLMResponse(text="pong", input_tokens=1, output_tokens=1)
    monkeypatch.setattr(
        "app.api.llm.ModelRouter",
        lambda *a, **kw: MagicMock(complete=MagicMock(return_value=fake_resp)),
    )
    r = client.post("/api/llm/ping", json={"prompt": "say hi"})
    assert r.status_code == 200
    data = r.json()
    assert data["text"] == "pong"
    assert data["input_tokens"] == 1


def test_llm_ping_handles_provider_error(client, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.api.llm.ModelRouter", lambda *a, **kw: MagicMock(complete=boom))
    r = client.post("/api/llm/ping", json={"prompt": "x"})
    assert r.status_code == 502
    assert "provider down" in r.json()["detail"]
