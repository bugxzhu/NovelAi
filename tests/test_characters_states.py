"""M3c-B: GET /api/characters/{id}/states endpoint."""
import json
from unittest.mock import MagicMock

import pytest

from app.llm.base import LLMResponse


@pytest.fixture
def fake_state_router(monkeypatch):
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {"new_characters": [], "updated_characters": [],
                         "new_lore": [], "updated_lore": []},
            "state_changes": [
                {"character_name": "李雷",
                 "state_snapshot": "愤怒", "change_summary": "被伏击"},
            ],
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    fake.embed = MagicMock(return_value=[[0.0] * 1024])
    monkeypatch.setattr("app.api.chapters_finalize.default_router", fake)
    return fake


def _setup_and_accept_state(client):
    """Finalize → accept the state_changes pending → return (pid, char_id, chapter_id)."""
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    cid = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷",
    }).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "第一章", "content": "x",
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    state_p = next(p for p in pendings if p["target_table"] == "character_states")
    client.post(f"/api/pending-updates/{state_p['id']}/accept")
    return pid, cid, ch


def test_list_states_404_unknown_character(client):
    r = client.get("/api/characters/99999/states")
    assert r.status_code == 404


def test_list_states_empty(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    cid = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷",
    }).json()["id"]
    r = client.get(f"/api/characters/{cid}/states")
    assert r.status_code == 200
    assert r.json() == []


def test_list_states_default_desc(client, fake_state_router):
    """Default order is desc (latest chapter first)."""
    pid, cid, ch1 = _setup_and_accept_state(client)
    # Add a second chapter + state
    ch2 = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 2, "title": "第二章", "content": "y",
    }).json()["id"]
    client.post(f"/api/chapters/{ch2}/finalize")
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    state_p = next(p for p in pendings
                   if p["target_table"] == "character_states" and p["status"] == "pending")
    client.post(f"/api/pending-updates/{state_p['id']}/accept")

    r = client.get(f"/api/characters/{cid}/states")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    # Desc: ch2 (order=2) first
    assert data[0]["chapter_order"] == 2
    assert data[1]["chapter_order"] == 1
    # Each row includes chapter_title and chapter_order join fields
    assert data[0]["chapter_title"] == "第二章"
    assert data[0]["state_snapshot"] == "愤怒"
    assert data[0]["change_summary"] == "被伏击"


def test_list_states_explicit_asc(client, fake_state_router):
    pid, cid, _ = _setup_and_accept_state(client)
    r = client.get(f"/api/characters/{cid}/states?order=asc")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["chapter_order"] == 1


def test_list_states_limit_cap(client, fake_state_router):
    """limit > 100 should be capped to 100."""
    pid, cid, _ = _setup_and_accept_state(client)
    r = client.get(f"/api/characters/{cid}/states?limit=500")
    assert r.status_code == 200  # not 422 — capped silently
