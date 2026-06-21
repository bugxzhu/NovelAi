"""M3c-C: /api/events endpoints."""
import pytest


def _seed_project_with_chapter(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    return pid, ch


def _create_event(client, pid, ch, title="x", foreshadows=None, **kwargs):
    body = {"project_id": pid, "chapter_id": ch, "title": title, "description": "d"}
    if foreshadows is not None:
        body["foreshadows"] = foreshadows
    body.update(kwargs)
    return client.post("/api/events", json=body).json()


def test_list_events_empty(client):
    pid, _ = _seed_project_with_chapter(client)
    r = client.get(f"/api/events?project_id={pid}")
    assert r.status_code == 200
    assert r.json() == []


def test_list_events_default_all(client):
    pid, ch = _seed_project_with_chapter(client)
    _create_event(client, pid, ch, title="A")
    _create_event(client, pid, ch, title="B")
    r = client.get(f"/api/events?project_id={pid}")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    titles = {e["title"] for e in data}
    assert titles == {"A", "B"}


def test_list_events_chapter_filter(client):
    pid, _ = _seed_project_with_chapter(client)
    ch1 = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    ch2 = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 2, "title": "C2", "content": "x",
    }).json()["id"]
    _create_event(client, pid, ch1, title="A")
    _create_event(client, pid, ch2, title="B")

    r = client.get(f"/api/events?project_id={pid}&chapter_id={ch1}")
    data = r.json()
    assert len(data) == 1
    assert data[0]["title"] == "A"


def test_list_events_payoff_of_derived(client):
    """A foreshadows B → B.payoff_of contains A. Wait — A foreshadows B means A is the foreshadow, B is the target. So B's payoff_of (events that foreshadow B) contains A."""
    pid, ch = _seed_project_with_chapter(client)
    a = _create_event(client, pid, ch, title="A")
    b = _create_event(client, pid, ch, title="B", foreshadows=[a["id"]])
    # B foreshadows A → A.payoff_of = [B], B.payoff_of = []

    r = client.get(f"/api/events?project_id={pid}")
    data = {e["title"]: e for e in r.json()}
    # B foreshadows A → A.payoff_of contains B
    assert data["A"]["payoff_of"] == [data["B"]["id"]]
    assert data["A"]["payoff_of_titles"] == ["B"]
    assert data["A"]["foreshadows"] == []
    assert data["B"]["foreshadows"] == [data["A"]["id"]]
    assert data["B"]["payoff_of"] == []


def test_list_events_filter_unpaid(client):
    """unpaid = foreshadows non-empty AND at least one target has empty payoff_of."""
    pid, ch = _seed_project_with_chapter(client)
    # C foreshadows B; B has no payoff → C is unpaid (because B is unpaid)
    b = _create_event(client, pid, ch, title="B")
    _create_event(client, pid, ch, title="C", foreshadows=[b["id"]])

    r = client.get(f"/api/events?project_id={pid}&filter=unpaid")
    data = r.json()
    titles = {e["title"] for e in data}
    assert titles == {"C"}  # C foreshadows B which is unpaid


def test_list_events_filter_paid(client):
    """paid = foreshadows non-empty AND all targets have payoff."""
    pid, ch = _seed_project_with_chapter(client)
    # A foreshadowed by B, C, D (all three foreshadow A → A has payoff)
    a = _create_event(client, pid, ch, title="A")
    client.post("/api/events", json={
        "project_id": pid, "chapter_id": ch, "title": "B", "description": "d",
        "foreshadows": [a["id"]],
    })
    client.post("/api/events", json={
        "project_id": pid, "chapter_id": ch, "title": "C", "description": "d",
        "foreshadows": [a["id"]],
    })
    client.post("/api/events", json={
        "project_id": pid, "chapter_id": ch, "title": "D", "description": "d",
        "foreshadows": [a["id"]],
    })

    r = client.get(f"/api/events?project_id={pid}&filter=paid")
    titles = {e["title"] for e in r.json()}
    assert titles == {"B", "C", "D"}  # all foreshadow A which has payoff


def test_list_events_involved_character_names_join(client):
    pid, ch = _seed_project_with_chapter(client)
    c1 = client.post("/api/characters", json={"project_id": pid, "name": "李雷"}).json()["id"]
    c2 = client.post("/api/characters", json={"project_id": pid, "name": "韩梅"}).json()["id"]
    client.post("/api/events", json={
        "project_id": pid, "chapter_id": ch,
        "title": "X", "description": "y",
        "involved_characters": [c1, c2],
    })
    r = client.get(f"/api/events?project_id={pid}")
    data = r.json()
    assert set(data[0]["involved_character_names"]) == {"李雷", "韩梅"}


def test_list_events_location_name_join(client):
    pid, ch = _seed_project_with_chapter(client)
    loc = client.post("/api/lore", json={
        "project_id": pid, "type": "location", "name": "残月酒馆",
    }).json()["id"]
    client.post("/api/events", json={
        "project_id": pid, "chapter_id": ch,
        "title": "X", "description": "y", "location_id": loc,
    })
    r = client.get(f"/api/events?project_id={pid}")
    data = r.json()
    assert data[0]["location_name"] == "残月酒馆"


def test_list_events_chapter_title_join(client):
    pid, ch = _seed_project_with_chapter(client)
    _create_event(client, pid, ch, title="X")
    r = client.get(f"/api/events?project_id={pid}")
    data = r.json()
    assert data[0]["chapter_title"] == "C1"
    assert data[0]["chapter_order"] == 1


def test_create_event_invalid_character_422(client):
    pid, ch = _seed_project_with_chapter(client)
    r = client.post("/api/events", json={
        "project_id": pid, "chapter_id": ch,
        "title": "X", "description": "y",
        "involved_characters": [99999],
    })
    assert r.status_code == 422


def test_create_event_invalid_location_422(client):
    pid, ch = _seed_project_with_chapter(client)
    r = client.post("/api/events", json={
        "project_id": pid, "chapter_id": ch,
        "title": "X", "description": "y", "location_id": 99999,
    })
    assert r.status_code == 422


def test_create_event_invalid_location_type_422(client):
    """location_id points to non-location lore → 422."""
    pid, ch = _seed_project_with_chapter(client)
    faction = client.post("/api/lore", json={
        "project_id": pid, "type": "faction", "name": "F",
    }).json()["id"]
    r = client.post("/api/events", json={
        "project_id": pid, "chapter_id": ch,
        "title": "X", "description": "y", "location_id": faction,
    })
    assert r.status_code == 422


def test_create_event_self_foreshadow_422(client):
    pid, ch = _seed_project_with_chapter(client)
    a = _create_event(client, pid, ch, title="A")
    r = client.patch(f"/api/events/{a['id']}", json={"foreshadows": [a["id"]]})
    assert r.status_code == 422


def test_create_event_invalid_foreshadow_target_422(client):
    pid, ch = _seed_project_with_chapter(client)
    r = client.post("/api/events", json={
        "project_id": pid, "chapter_id": ch,
        "title": "X", "description": "y", "foreshadows": [99999],
    })
    assert r.status_code == 422


def test_patch_event_add_foreshadow(client):
    pid, ch = _seed_project_with_chapter(client)
    a = _create_event(client, pid, ch, title="A")
    b = _create_event(client, pid, ch, title="B")
    r = client.patch(f"/api/events/{a['id']}", json={"foreshadows": [b["id"]]})
    assert r.status_code == 200
    assert r.json()["foreshadows"] == [b["id"]]


def test_patch_event_remove_foreshadow(client):
    pid, ch = _seed_project_with_chapter(client)
    b = _create_event(client, pid, ch, title="B")
    a = _create_event(client, pid, ch, title="A", foreshadows=[b["id"]])
    r = client.patch(f"/api/events/{a['id']}", json={"foreshadows": []})
    assert r.status_code == 200
    assert r.json()["foreshadows"] == []


def test_patch_event_replace_foreshadows(client):
    """PATCH sends full array; replaces entirely."""
    pid, ch = _seed_project_with_chapter(client)
    a = _create_event(client, pid, ch, title="A")
    b = _create_event(client, pid, ch, title="B")
    c = _create_event(client, pid, ch, title="C")
    client.patch(f"/api/events/{a['id']}", json={"foreshadows": [b["id"]]})
    r = client.patch(f"/api/events/{a['id']}", json={"foreshadows": [c["id"]]})
    assert r.status_code == 200
    assert r.json()["foreshadows"] == [c["id"]]


def test_patch_event_other_fields(client):
    pid, ch = _seed_project_with_chapter(client)
    e = _create_event(client, pid, ch, title="X")
    r = client.patch(f"/api/events/{e['id']}", json={
        "title": "Y", "description": "new desc",
    })
    assert r.status_code == 200
    assert r.json()["title"] == "Y"
    assert r.json()["description"] == "new desc"


def test_delete_event_cleans_dangling_foreshadows(client):
    """Deleting event X removes X from all other events' foreshadows."""
    pid, ch = _seed_project_with_chapter(client)
    x = _create_event(client, pid, ch, title="X")
    a = _create_event(client, pid, ch, title="A", foreshadows=[x["id"]])
    b = _create_event(client, pid, ch, title="B", foreshadows=[x["id"]])

    r = client.delete(f"/api/events/{x['id']}")
    assert r.status_code == 204

    a_after = client.get(f"/api/events/{a['id']}").json()
    b_after = client.get(f"/api/events/{b['id']}").json()
    assert a_after["foreshadows"] == []
    assert b_after["foreshadows"] == []


def test_get_event_404(client):
    r = client.get("/api/events/99999")
    assert r.status_code == 404


def test_list_requires_project_id(client):
    r = client.get("/api/events")
    assert r.status_code == 422


def test_list_events_filter_with_pagination(client):
    """Filter applied BEFORE pagination — small limit doesn't hide results."""
    pid, ch = _seed_project_with_chapter(client)
    # Create 5 events. Event 1 has foreshadows but no other event references its target → unpaid.
    # Events 2-5 are plain (no foreshadows) → excluded from unpaid filter.
    target = _create_event(client, pid, ch, title="T")  # plain target
    _create_event(client, pid, ch, title="Unpaid1", foreshadows=[target["id"]])
    _create_event(client, pid, ch, title="Plain2")
    _create_event(client, pid, ch, title="Plain3")
    _create_event(client, pid, ch, title="Plain4")

    # With limit=1 and filter=unpaid, should still find "Unpaid1" even though
    # by id order it's the 2nd event. (Filter applies before pagination.)
    r = client.get(f"/api/events?project_id={pid}&filter=unpaid&limit=1&offset=0")
    data = r.json()
    assert len(data) == 1
    assert data[0]["title"] == "Unpaid1"
