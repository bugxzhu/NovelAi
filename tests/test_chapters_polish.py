"""POST /api/chapters/{id}/polish API tests."""
import json
from unittest.mock import MagicMock

import pytest

from app.llm.base import LLMResponse


@pytest.fixture
def fake_polish_router(monkeypatch):
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-sonnet-4-6"))
    fake.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({"versions": ["润色结果。"]}),
        input_tokens=10, output_tokens=20, stop_reason="end_turn",
    ))
    monkeypatch.setattr("app.api.chapters_polish.default_router", fake)
    return fake


def _seed(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "原文",
    }).json()["id"]
    return pid, ch


def test_polish_returns_404_unknown_chapter(client):
    r = client.post("/api/chapters/99999/polish", json={})
    assert r.status_code == 404


def test_polish_success(client, fake_polish_router):
    pid, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/polish", json={})
    assert r.status_code == 200
    data = r.json()
    assert data["polished_texts"] == ["润色结果。"]
    assert data["is_selection"] is False
    assert data["direction"] == ""
    assert data["log_id"] > 0


def test_polish_with_selection(client, fake_polish_router):
    # For selection, the API expects 2 versions; reconfigure the mock.
    fake_polish_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({"versions": ["版本A", "版本B"]}),
        input_tokens=10, output_tokens=20, stop_reason="end_turn",
    ))
    pid, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/polish", json={"selected_text": "选中文字"})
    assert r.status_code == 200
    data = r.json()
    assert data["is_selection"] is True
    assert len(data["polished_texts"]) == 2


def test_polish_with_direction(client, fake_polish_router):
    pid, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/polish", json={"direction": "增加心理描写"})
    assert r.status_code == 200
    assert r.json()["direction"] == "增加心理描写"


def test_polish_llm_failure_returns_502(client, fake_polish_router):
    pid, ch = _seed(client)
    fake_polish_router.complete = MagicMock(side_effect=RuntimeError("network"))
    r = client.post(f"/api/chapters/{ch}/polish", json={})
    assert r.status_code == 502


def test_polish_max_tokens_returns_422(client, fake_polish_router):
    pid, ch = _seed(client)
    fake_polish_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({"versions": ["截断"]}),
        input_tokens=10, output_tokens=20, stop_reason="max_tokens",
    ))
    r = client.post(f"/api/chapters/{ch}/polish", json={})
    assert r.status_code == 422
    assert "polish_failed" in str(r.json())
