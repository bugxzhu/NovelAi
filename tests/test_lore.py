def _make_project(client):
    return client.post("/api/projects", json={"title": "X"}).json()["id"]


def test_create_lore_entry(client):
    pid = _make_project(client)
    r = client.post(
        "/api/lore",
        json={"project_id": pid, "type": "location", "name": "青石镇", "tags": ["北方"]},
    )
    assert r.status_code == 201
    assert r.json()["name"] == "青石镇"
    assert r.json()["tags"] == ["北方"]


def test_list_lore_by_project(client):
    pid = _make_project(client)
    client.post("/api/lore", json={"project_id": pid, "type": "location", "name": "A"})
    client.post("/api/lore", json={"project_id": pid, "type": "faction", "name": "B"})
    # 另一个项目
    pid2 = _make_project(client)
    client.post("/api/lore", json={"project_id": pid2, "type": "location", "name": "C"})
    r = client.get(f"/api/lore?project_id={pid}")
    assert r.status_code == 200
    names = {x["name"] for x in r.json()}
    assert names == {"A", "B"}


def test_list_lore_filter_by_type(client):
    pid = _make_project(client)
    client.post("/api/lore", json={"project_id": pid, "type": "location", "name": "A"})
    client.post("/api/lore", json={"project_id": pid, "type": "faction", "name": "B"})
    r = client.get(f"/api/lore?project_id={pid}&type=faction")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["name"] == "B"


def test_lore_parent_hierarchy(client):
    pid = _make_project(client)
    parent = client.post(
        "/api/lore", json={"project_id": pid, "type": "location", "name": "王国"}
    ).json()["id"]
    child = client.post(
        "/api/lore",
        json={"project_id": pid, "type": "location", "name": "王城", "parent_id": parent},
    ).json()
    assert child["parent_id"] == parent


def test_update_lore_entry(client):
    pid = _make_project(client)
    lid = client.post(
        "/api/lore", json={"project_id": pid, "type": "item", "name": "Old"}
    ).json()["id"]
    r = client.patch(f"/api/lore/{lid}", json={"name": "New"})
    assert r.status_code == 200
    assert r.json()["name"] == "New"


def test_delete_lore_entry(client):
    pid = _make_project(client)
    lid = client.post(
        "/api/lore", json={"project_id": pid, "type": "item", "name": "X"}
    ).json()["id"]
    r = client.delete(f"/api/lore/{lid}")
    assert r.status_code == 204
