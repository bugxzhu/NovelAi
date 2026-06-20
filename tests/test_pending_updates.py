import json
from unittest.mock import MagicMock

import pytest

from app.llm.base import LLMResponse


@pytest.fixture
def fake_router(monkeypatch):
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {
                "new_characters": [
                    {"name": "韩梅", "role": "supporting", "description": "老板娘"}
                ],
                "updated_characters": [],
                "new_lore": [
                    {"type": "location", "name": "残月酒馆", "description": "酒馆"}
                ],
                "updated_lore": [],
            }
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    monkeypatch.setattr("app.api.chapters_finalize.default_router", fake)
    return fake


def _seed_and_finalize(client, fake_router):
    """Create project + character + chapter + finalize → produces 1 char pending + 1 lore pending."""
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    char = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷", "background": "old bg"
    }).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1",
        "content": "x"
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")
    return pid, char, ch


def test_list_requires_project_id(client):
    r = client.get("/api/pending-updates")
    assert r.status_code == 422


def test_list_returns_pending_by_default(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    r = client.get(f"/api/pending-updates?project_id={pid}")
    assert r.status_code == 200
    pendings = r.json()
    assert len(pendings) == 2
    statuses = {p["status"] for p in pendings}
    assert statuses == {"pending"}


def test_list_status_filter(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    first_id = pendings[0]["id"]
    # Accept it
    client.post(f"/api/pending-updates/{first_id}/accept")
    # status=pending should return 1
    r1 = client.get(f"/api/pending-updates?project_id={pid}&status=pending")
    assert len(r1.json()) == 1
    # status=accepted should return 1
    r2 = client.get(f"/api/pending-updates?project_id={pid}&status=accepted")
    assert len(r2.json()) == 1


def test_list_chapter_filter(client, fake_router):
    pid, _, ch = _seed_and_finalize(client, fake_router)
    # Add another chapter, finalize
    ch2 = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 2, "title": "C2", "content": "y"
    }).json()["id"]
    client.post(f"/api/chapters/{ch2}/finalize")
    r = client.get(f"/api/pending-updates?project_id={pid}&chapter_id={ch}")
    assert all(p["chapter_id"] == ch for p in r.json())


def test_detail_returns_full_proposed_change(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    first_id = pendings[0]["id"]
    r = client.get(f"/api/pending-updates/{first_id}")
    assert r.status_code == 200
    detail = r.json()
    assert "proposed_change" in detail
    assert detail["chapter_title"]


def test_detail_404_unknown(client):
    r = client.get("/api/pending-updates/99999")
    assert r.status_code == 404


def test_accept_create_character(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    char_pending = next(p for p in pendings if p["target_table"] == "characters")
    r = client.post(f"/api/pending-updates/{char_pending['id']}/accept")
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"
    # Character created
    chars = client.get(f"/api/characters?project_id={pid}").json()
    names = {c["name"] for c in chars}
    assert "韩梅" in names


def test_accept_create_lore(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    lore_pending = next(p for p in pendings if p["target_table"] == "lore_entries")
    r = client.post(f"/api/pending-updates/{lore_pending['id']}/accept")
    assert r.status_code == 200
    lore = client.get(f"/api/lore?project_id={pid}").json()
    names = {l["name"] for l in lore}
    assert "残月酒馆" in names


def test_accept_update_character(client, monkeypatch):
    """Accept an update pending → field on existing character changes."""
    fake = MagicMock()
    fake.resolve_model = MagicMock(return_value=("claude", "claude-haiku-4-5"))
    fake.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {
                "new_characters": [],
                "updated_characters": [
                    {"name": "李雷", "field": "background", "new_value": "new bg"}
                ],
                "new_lore": [],
                "updated_lore": [],
            }
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    monkeypatch.setattr("app.api.chapters_finalize.default_router", fake)

    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    char = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷", "background": "old bg"
    }).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x"
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")

    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    assert len(pendings) == 1
    r = client.post(f"/api/pending-updates/{pendings[0]['id']}/accept")
    assert r.status_code == 200

    # Character updated
    c = client.get(f"/api/characters/{char}").json()
    assert c["background"] == "new bg"


def test_accept_already_decided_returns_409(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    first_id = pendings[0]["id"]
    r1 = client.post(f"/api/pending-updates/{first_id}/accept")
    assert r1.status_code == 200
    r2 = client.post(f"/api/pending-updates/{first_id}/accept")
    assert r2.status_code == 409


def test_reject_marks_status(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    first_id = pendings[0]["id"]
    r = client.post(f"/api/pending-updates/{first_id}/reject", json={"note": "不准"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    # Verify detail has note
    detail = client.get(f"/api/pending-updates/{first_id}").json()
    assert detail["decision_note"] == "不准"


def test_reject_does_not_touch_target(client, fake_router):
    pid, _, _ = _seed_and_finalize(client, fake_router)
    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    char_pending = next(p for p in pendings if p["target_table"] == "characters")
    client.post(f"/api/pending-updates/{char_pending['id']}/reject")
    chars = client.get(f"/api/characters?project_id={pid}").json()
    assert all(c["name"] != "韩梅" for c in chars)  # not created


def test_accept_character_state_inserts_row_and_mirrors_current_state(client, fake_router):
    """Accept a character_states pending → INSERT character_states row + UPDATE characters.current_state."""
    # Override fake_router.complete to return state_changes
    fake_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {"new_characters": [], "updated_characters": [],
                         "new_lore": [], "updated_lore": []},
            "state_changes": [
                {"character_name": "李雷",
                 "state_snapshot": "愤怒且受伤",
                 "change_summary": "被伏击"}
            ],
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    # M3b embed mock
    fake_router.embed = MagicMock(return_value=[[0.0] * 1024])

    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    cid = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷", "current_state": "警惕",
    }).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")

    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    state_pending = next(p for p in pendings if p["target_table"] == "character_states")
    assert state_pending["update_type"] == "soft_fact"
    assert state_pending["entity_name"] == "李雷"
    assert state_pending["proposed_value"] == "愤怒且受伤"

    r = client.post(f"/api/pending-updates/{state_pending['id']}/accept")
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"

    # Mirror: characters.current_state updated
    char = client.get(f"/api/characters/{cid}").json()
    assert char["current_state"] == "愤怒且受伤"

    # Direct DB check: character_states row exists
    from app.memory import session as sm
    from app.memory.schema import CharacterState
    with sm.SessionLocal() as s:
        rows = list(s.query(CharacterState).filter(CharacterState.character_id == cid))
    assert len(rows) == 1
    assert rows[0].state_snapshot == "愤怒且受伤"
    assert rows[0].change_summary == "被伏击"
    assert rows[0].extractor_log_id is not None
    assert rows[0].pending_update_id == state_pending["id"]


def test_accept_character_state_target_gone_returns_500(client, fake_router):
    """If the character was deleted before accept → 500."""
    fake_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {"new_characters": [], "updated_characters": [],
                         "new_lore": [], "updated_lore": []},
            "state_changes": [{"character_name": "李雷",
                               "state_snapshot": "x", "change_summary": ""}],
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    fake_router.embed = MagicMock(return_value=[[0.0] * 1024])

    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    cid = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷",
    }).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")

    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    state_pending = next(p for p in pendings if p["target_table"] == "character_states")

    # Delete the character (cascades: but pending_update rows have target_table='character_states'
    # with target_id=null, so they survive)
    client.delete(f"/api/characters/{cid}")

    r = client.post(f"/api/pending-updates/{state_pending['id']}/accept")
    assert r.status_code == 500


def test_reject_character_state_no_db_change(client, fake_router):
    """Reject → no character_states row, no current_state change."""
    fake_router.complete = MagicMock(return_value=LLMResponse(
        text=json.dumps({
            "summary": "x",
            "entities": {"new_characters": [], "updated_characters": [],
                         "new_lore": [], "updated_lore": []},
            "state_changes": [{"character_name": "李雷",
                               "state_snapshot": "x", "change_summary": ""}],
        }),
        input_tokens=1, output_tokens=1, stop_reason="end_turn",
    ))
    fake_router.embed = MagicMock(return_value=[[0.0] * 1024])

    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    cid = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷", "current_state": "警惕",
    }).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    client.post(f"/api/chapters/{ch}/finalize")

    pendings = client.get(f"/api/pending-updates?project_id={pid}").json()
    state_pending = next(p for p in pendings if p["target_table"] == "character_states")

    r = client.post(f"/api/pending-updates/{state_pending['id']}/reject",
                    json={"note": "no"})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"

    # current_state unchanged
    char = client.get(f"/api/characters/{cid}").json()
    assert char["current_state"] == "警惕"

    # No character_states row
    from app.memory import session as sm
    from app.memory.schema import CharacterState
    with sm.SessionLocal() as s:
        rows = list(s.query(CharacterState).filter(CharacterState.character_id == cid))
    assert rows == []
