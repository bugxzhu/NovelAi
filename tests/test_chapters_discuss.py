"""M4b-2: POST /api/chapters/{id}/discuss endpoint tests."""
import json
from unittest.mock import MagicMock

import pytest

from app.llm.base import LLMResponse


@pytest.fixture
def fake_discuss_router(monkeypatch):
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-sonnet-4-6"))
    fake.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({"branches": [], "recommended": "A", "reasoning": "r"}),
        input_tokens=10, output_tokens=20, stop_reason="end_turn",
    ))
    monkeypatch.setattr("app.api.chapters_discuss.default_router", fake)
    return fake


def _seed(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    return pid, ch


def test_discuss_returns_404_unknown_chapter(client):
    r = client.post("/api/chapters/99999/discuss", json={"question": "如果？"})
    assert r.status_code == 404


def test_discuss_success(client, fake_discuss_router):
    pid, ch = _seed(client)
    fake_discuss_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "branches": [
                {"label": "A", "title": "和解", "summary": "s",
                 "conflicts": "c", "opportunities": "o",
                 "character_impact": "i"},
                {"label": "B", "title": "决裂", "summary": "s",
                 "conflicts": "c", "opportunities": "o",
                 "character_impact": "i"},
                {"label": "C", "title": "搁置", "summary": "s",
                 "conflicts": "c", "opportunities": "o",
                 "character_impact": "i"},
            ],
            "recommended": "A",
            "reasoning": "A 最稳",
        }),
        input_tokens=10, output_tokens=20, stop_reason="end_turn",
    ))
    r = client.post(f"/api/chapters/{ch}/discuss",
                    json={"question": "如果让李雷和韩梅和解？"})
    assert r.status_code == 200
    data = r.json()
    assert data["question"] == "如果让李雷和韩梅和解？"
    assert len(data["branches"]) == 3
    assert data["branches"][0]["label"] == "A"
    assert data["recommended"] == "A"
    assert data["reasoning"] == "A 最稳"
    assert data["log_id"] > 0


def test_discuss_llm_failure_returns_502(client, fake_discuss_router):
    pid, ch = _seed(client)
    fake_discuss_router.complete = MagicMock(side_effect=RuntimeError("network"))
    r = client.post(f"/api/chapters/{ch}/discuss", json={"question": "如果？"})
    assert r.status_code == 502


def test_discuss_invalid_json_returns_422(client, fake_discuss_router):
    pid, ch = _seed(client)
    fake_discuss_router.complete = MagicMock(return_value=LLMResponse(
        text="not json",
        input_tokens=10, output_tokens=20, stop_reason="end_turn",
    ))
    r = client.post(f"/api/chapters/{ch}/discuss", json={"question": "如果？"})
    assert r.status_code == 422
    assert "discuss_failed" in str(r.json())
