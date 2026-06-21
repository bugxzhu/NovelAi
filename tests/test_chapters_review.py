"""M4a: POST /api/chapters/{id}/review endpoint tests."""
import json
from unittest.mock import MagicMock

import pytest

from app.llm.base import LLMResponse


@pytest.fixture
def fake_review_router(monkeypatch):
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-sonnet-4-6"))
    fake.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({"issues_by_category": {}}),
        input_tokens=10, output_tokens=20, stop_reason="end_turn",
    ))
    monkeypatch.setattr("app.api.chapters_review.default_router", fake)
    return fake


def _seed(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    return pid, ch


def test_review_returns_404_unknown_chapter(client):
    r = client.post("/api/chapters/99999/review")
    assert r.status_code == 404


def test_review_success(client, fake_review_router):
    pid, ch = _seed(client)
    fake_review_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({"issues_by_category": {
            "character": [
                {"severity": "warn", "location": "x",
                 "description": "y", "suggestion": ""},
            ],
        }}),
        input_tokens=10, output_tokens=20, stop_reason="end_turn",
    ))
    r = client.post(f"/api/chapters/{ch}/review")
    assert r.status_code == 200
    data = r.json()
    assert data["chapter_id"] == ch
    assert len(data["issues"]) == 1
    assert data["issues"][0]["category"] == "character"
    assert data["log_id"] > 0


def test_review_llm_failure_returns_502(client, fake_review_router):
    pid, ch = _seed(client)
    fake_review_router.complete = MagicMock(side_effect=RuntimeError("network"))
    r = client.post(f"/api/chapters/{ch}/review")
    assert r.status_code == 502


def test_review_invalid_json_returns_422(client, fake_review_router):
    pid, ch = _seed(client)
    fake_review_router.complete = MagicMock(return_value=LLMResponse(
        text="not json",
        input_tokens=10, output_tokens=20, stop_reason="end_turn",
    ))
    r = client.post(f"/api/chapters/{ch}/review")
    assert r.status_code == 422
    assert "review_failed" in str(r.json())


def test_review_max_tokens_returns_422(client, fake_review_router):
    pid, ch = _seed(client)
    fake_review_router.complete = MagicMock(return_value=LLMResponse(
        text="{truncated",
        input_tokens=10, output_tokens=20, stop_reason="max_tokens",
    ))
    r = client.post(f"/api/chapters/{ch}/review")
    assert r.status_code == 422
