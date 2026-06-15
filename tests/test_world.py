def _make_project(client):
    return client.post("/api/projects", json={"title": "X"}).json()["id"]


def test_upsert_world_overview_creates(client):
    pid = _make_project(client)
    r = client.put(
        f"/api/projects/{pid}/world-overview",
        json={"setting_era": "中古", "power_system": "魔法"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["project_id"] == pid
    assert data["setting_era"] == "中古"
    assert data["power_system"] == "魔法"


def test_upsert_world_overview_updates(client):
    pid = _make_project(client)
    client.put(f"/api/projects/{pid}/world-overview", json={"setting_era": "A"})
    r = client.put(f"/api/projects/{pid}/world-overview", json={"setting_era": "B"})
    assert r.status_code == 200
    assert r.json()["setting_era"] == "B"


def test_get_world_overview(client):
    pid = _make_project(client)
    client.put(f"/api/projects/{pid}/world-overview", json={"geography_summary": "山海之间"})
    r = client.get(f"/api/projects/{pid}/world-overview")
    assert r.status_code == 200
    assert r.json()["geography_summary"] == "山海之间"


def test_get_world_overview_not_found(client):
    pid = _make_project(client)
    r = client.get(f"/api/projects/{pid}/world-overview")
    assert r.status_code == 404


def test_get_world_overview_project_not_found(client):
    r = client.get("/api/projects/9999/world-overview")
    assert r.status_code == 404
