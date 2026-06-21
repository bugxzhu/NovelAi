"""M3c-D: /api/plot-lines CRUD tests."""


def _seed(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    return pid, ch


def test_list_empty(client):
    pid, _ = _seed(client)
    r = client.get(f"/api/plot-lines?project_id={pid}")
    assert r.status_code == 200
    assert r.json() == []


def test_create_defaults(client):
    pid, _ = _seed(client)
    r = client.post("/api/plot-lines", json={
        "project_id": pid, "title": "复仇之路",
    })
    assert r.status_code == 201
    assert r.json()["type"] == "sub"
    assert r.json()["status"] == "planned"


def test_create_with_all_fields(client):
    pid, ch = _seed(client)
    r = client.post("/api/plot-lines", json={
        "project_id": pid, "type": "main", "title": "主线",
        "summary": "进展", "description": "关于",
        "status": "active", "start_chapter": ch,
    })
    assert r.status_code == 201
    data = r.json()
    assert data["type"] == "main"
    assert data["status"] == "active"
    assert data["start_chapter"] == ch


def test_list_status_filter(client):
    pid, _ = _seed(client)
    client.post("/api/plot-lines", json={
        "project_id": pid, "title": "A", "status": "active",
    })
    client.post("/api/plot-lines", json={
        "project_id": pid, "title": "B", "status": "planned",
    })
    r = client.get(f"/api/plot-lines?project_id={pid}&status=active")
    data = r.json()
    assert len(data) == 1
    assert data[0]["title"] == "A"


def test_list_main_before_sub(client):
    """main type sorts before sub."""
    pid, _ = _seed(client)
    client.post("/api/plot-lines", json={
        "project_id": pid, "title": "Sub", "type": "sub",
    })
    client.post("/api/plot-lines", json={
        "project_id": pid, "title": "Main", "type": "main",
    })
    r = client.get(f"/api/plot-lines?project_id={pid}")
    data = r.json()
    assert data[0]["title"] == "Main"
    assert data[1]["title"] == "Sub"


def test_patch(client):
    pid, _ = _seed(client)
    create_r = client.post("/api/plot-lines", json={
        "project_id": pid, "title": "X",
    })
    rid = create_r.json()["id"]
    r = client.patch(f"/api/plot-lines/{rid}", json={
        "status": "resolved", "summary": "已完结",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"
    assert r.json()["summary"] == "已完结"


def test_delete(client):
    pid, _ = _seed(client)
    create_r = client.post("/api/plot-lines", json={
        "project_id": pid, "title": "X",
    })
    rid = create_r.json()["id"]
    r = client.delete(f"/api/plot-lines/{rid}")
    assert r.status_code == 204
    assert client.get(f"/api/plot-lines?project_id={pid}").json() == []


def test_list_requires_project_id(client):
    r = client.get("/api/plot-lines")
    assert r.status_code == 422
