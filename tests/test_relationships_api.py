"""M3c-A: /api/relationships endpoints."""
import pytest


def _seed_project_with_two_characters(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    c1 = client.post("/api/characters", json={"project_id": pid, "name": "李雷"}).json()["id"]
    c2 = client.post("/api/characters", json={"project_id": pid, "name": "韩梅"}).json()["id"]
    return pid, c1, c2


def test_list_relationships_empty(client):
    pid, _, _ = _seed_project_with_two_characters(client)
    r = client.get(f"/api/relationships?project_id={pid}")
    assert r.status_code == 200
    assert r.json() == []


def test_create_relationship_default_valid_from_zero(client):
    pid, c1, c2 = _seed_project_with_two_characters(client)
    r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友", "strength": 0.5,
    })
    assert r.status_code == 201
    data = r.json()
    assert data["from_char_name"] == "李雷"
    assert data["to_char_name"] == "韩梅"
    assert data["valid_from_chapter"] == 0
    assert data["valid_to_chapter"] is None


def test_create_relationship_self_reference_422(client):
    pid, c1, _ = _seed_project_with_two_characters(client)
    r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c1,
        "type": "自我",
    })
    assert r.status_code == 422


def test_create_relationship_partial_unique_conflict_409(client):
    pid, c1, c2 = _seed_project_with_two_characters(client)
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友",
    })
    r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "仇人",
    })
    assert r.status_code == 409


def test_create_relationship_strength_clamped(client):
    pid, c1, c2 = _seed_project_with_two_characters(client)
    r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "x", "strength": 1.5,
    })
    assert r.status_code == 201
    assert r.json()["strength"] == 1.0


def test_create_reverse_direction_allowed(client):
    """A→B and B→A can both be current-valid (independent records)."""
    pid, c1, c2 = _seed_project_with_two_characters(client)
    r1 = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "暗恋",
    })
    r2 = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c2, "to_char_id": c1,
        "type": "朋友",
    })
    assert r1.status_code == 201
    assert r2.status_code == 201


def test_list_relationships_default_current_only(client):
    """Default: only valid_to IS NULL."""
    pid, c1, c2 = _seed_project_with_two_characters(client)
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友", "valid_from_chapter": 0,
    })
    old_id = client.get(f"/api/relationships?project_id={pid}").json()[0]["id"]
    client.post(f"/api/relationships/{old_id}/soft-close", json={"valid_to_chapter": ch})
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "仇人", "valid_from_chapter": ch,
    })

    r = client.get(f"/api/relationships?project_id={pid}")
    data = r.json()
    assert len(data) == 1
    assert data[0]["type"] == "仇人"


def test_list_relationships_include_history(client):
    pid, c1, c2 = _seed_project_with_two_characters(client)
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友", "valid_from_chapter": 0,
    })
    old_id = client.get(f"/api/relationships?project_id={pid}").json()[0]["id"]
    client.post(f"/api/relationships/{old_id}/soft-close", json={"valid_to_chapter": ch})
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "仇人", "valid_from_chapter": ch,
    })

    r = client.get(f"/api/relationships?project_id={pid}&include_history=true")
    data = r.json()
    assert len(data) == 2


def test_relationship_history_endpoint_desc(client):
    """GET /api/relationships/history?from=X&to=Y → versions in desc order."""
    pid, c1, c2 = _seed_project_with_two_characters(client)
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友", "valid_from_chapter": 0,
    })
    old_id = client.get(f"/api/relationships?project_id={pid}").json()[0]["id"]
    client.post(f"/api/relationships/{old_id}/soft-close", json={"valid_to_chapter": ch})
    client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "仇人", "valid_from_chapter": ch,
    })

    r = client.get(f"/api/relationships/history?from_char_id={c1}&to_char_id={c2}")
    data = r.json()
    assert len(data) == 2
    # Desc by valid_from_chapter
    assert data[0]["valid_from_chapter"] == ch  # newer
    assert data[0]["valid_to_chapter"] is None
    assert data[1]["valid_from_chapter"] == 0
    assert data[1]["valid_to_chapter"] == ch


def test_relationship_history_empty_when_no_data(client):
    pid, c1, c2 = _seed_project_with_two_characters(client)
    r = client.get(f"/api/relationships/history?from_char_id={c1}&to_char_id={c2}")
    assert r.status_code == 200
    assert r.json() == []


def test_patch_relationship_only_allowed_fields(client):
    pid, c1, c2 = _seed_project_with_two_characters(client)
    create_r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友", "strength": 0.5,
    })
    rid = create_r.json()["id"]

    r = client.patch(f"/api/relationships/{rid}", json={
        "type": "盟友", "strength": 0.7, "description": "更紧密",
    })
    assert r.status_code == 200
    assert r.json()["type"] == "盟友"
    assert r.json()["strength"] == 0.7
    assert r.json()["description"] == "更紧密"


def test_patch_relationship_ignores_valid_fields(client):
    """PATCH body with valid_from/to should be ignored (Pydantic schema drops them)."""
    pid, c1, c2 = _seed_project_with_two_characters(client)
    create_r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友", "valid_from_chapter": 0,
    })
    rid = create_r.json()["id"]
    original_valid_from = create_r.json()["valid_from_chapter"]

    # Pydantic schema doesn't include valid_* fields, so they're silently dropped
    r = client.patch(f"/api/relationships/{rid}", json={
        "type": "盟友",
        "valid_from_chapter": 99,  # not in schema → ignored
    })
    assert r.status_code == 200
    assert r.json()["valid_from_chapter"] == original_valid_from


def test_soft_close_relationship(client):
    pid, c1, c2 = _seed_project_with_two_characters(client)
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    create_r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友",
    })
    rid = create_r.json()["id"]

    r = client.post(f"/api/relationships/{rid}/soft-close",
                    json={"valid_to_chapter": ch})
    assert r.status_code == 200
    assert r.json()["valid_to_chapter"] == ch


def test_delete_current_returns_409(client):
    """Cannot physically delete a current-valid relationship."""
    pid, c1, c2 = _seed_project_with_two_characters(client)
    create_r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友",
    })
    rid = create_r.json()["id"]

    r = client.delete(f"/api/relationships/{rid}")
    assert r.status_code == 409


def test_delete_history_ok(client):
    """Can physically delete a soft-closed (history) relationship."""
    pid, c1, c2 = _seed_project_with_two_characters(client)
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    create_r = client.post("/api/relationships", json={
        "project_id": pid, "from_char_id": c1, "to_char_id": c2,
        "type": "旧友",
    })
    rid = create_r.json()["id"]
    client.post(f"/api/relationships/{rid}/soft-close", json={"valid_to_chapter": ch})

    r = client.delete(f"/api/relationships/{rid}")
    assert r.status_code == 204


def test_get_relationship_404(client):
    r = client.get("/api/relationships/99999")
    assert r.status_code == 404


def test_list_requires_project_id(client):
    r = client.get("/api/relationships")
    assert r.status_code == 422
