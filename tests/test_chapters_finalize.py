import json
from unittest.mock import MagicMock

import pytest

from app.llm.base import LLMResponse


@pytest.fixture
def fake_router(monkeypatch):
    """Patch default_router at the endpoint module."""
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "李雷进入酒馆。",
            "entities": {
                "new_characters": [{"name": "韩梅", "role": "supporting", "description": "老板娘"}],
                "updated_characters": [],
                "new_lore": [],
                "updated_lore": [],
            }
        }),
        input_tokens=100, output_tokens=200, stop_reason="end_turn",
    ))
    monkeypatch.setattr("app.api.chapters_finalize.default_router", fake)
    return fake


def _seed(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1",
        "content": "夜色压在屋脊上。"
    }).json()["id"]
    return pid, ch


def test_finalize_returns_404_unknown_chapter(client, fake_router):
    r = client.post("/api/chapters/99999/finalize")
    assert r.status_code == 404
    assert r.json()["detail"] == "chapter not found"


def test_finalize_success(client, fake_router):
    pid, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/finalize")
    assert r.status_code == 200
    data = r.json()
    assert data["chapter_id"] == ch
    assert data["summary"] == "李雷进入酒馆。"
    assert data["pending_created"] == 1
    assert data["log_id"] > 0

    # Verify chapter was updated
    chap = client.get(f"/api/chapters/{ch}").json()
    assert chap["summary"] == "李雷进入酒馆。"
    assert chap["status"] == "final"
    assert chap["content_hash"]


def test_finalize_llm_failure_returns_502(client, monkeypatch):
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(side_effect=RuntimeError("API down"))
    monkeypatch.setattr("app.api.chapters_finalize.default_router", fake)
    pid, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/finalize")
    assert r.status_code == 502
    assert "API down" in r.json()["detail"]


def test_finalize_invalid_json_returns_422(client, monkeypatch):
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=LLMResponse(
        text="not json {{",
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    monkeypatch.setattr("app.api.chapters_finalize.default_router", fake)
    pid, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/finalize")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "extraction_failed"
    assert "raw" in detail


def test_finalize_idempotent(client, fake_router):
    pid, ch = _seed(client)
    r1 = client.post(f"/api/chapters/{ch}/finalize")
    assert r1.status_code == 200
    # Second call should also succeed and overwrite pending
    r2 = client.post(f"/api/chapters/{ch}/finalize")
    assert r2.status_code == 200
    assert r2.json()["pending_created"] == 1  # same data → same count
