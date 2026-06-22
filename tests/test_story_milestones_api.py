"""M4b-1: /api/story-milestones CRUD tests."""


def _seed(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x",
    }).json()["id"]
    return pid, ch


def test_list_empty(client):
    pid, _ = _seed(client)
    r = client.get(f"/api/story-milestones?project_id={pid}")
    assert r.status_code == 200
    assert r.json() == []


def test_create_defaults(client):
    pid, _ = _seed(client)
    r = client.post("/api/story-milestones", json={
        "project_id": pid, "title": "第一转折",
    })
    assert r.status_code == 201
    assert r.json()["type"] == "里程碑"
    assert r.json()["status"] == "planned"
    assert r.json()["order_index"] == 0


def test_create_with_all_fields(client):
    pid, ch = _seed(client)
    r = client.post("/api/story-milestones", json={
        "project_id": pid, "order_index": 5, "type": "高潮",
        "title": "决战", "description": "终极对决",
        "chapter_start": ch, "chapter_end": ch,
        "status": "active",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["order_index"] == 5
    assert data["type"] == "高潮"
    assert data["status"] == "active"
    assert data["chapter_start"] == ch
    assert data["chapter_end"] == ch
    assert data["description"] == "终极对决"


def test_list_ordered_by_order_index(client):
    pid, _ = _seed(client)
    client.post("/api/story-milestones", json={
        "project_id": pid, "title": "Late", "order_index": 10,
    })
    client.post("/api/story-milestones", json={
        "project_id": pid, "title": "Early", "order_index": 1,
    })
    client.post("/api/story-milestones", json={
        "project_id": pid, "title": "Mid", "order_index": 5,
    })
    r = client.get(f"/api/story-milestones?project_id={pid}")
    data = r.json()
    assert [d["title"] for d in data] == ["Early", "Mid", "Late"]


def test_patch(client):
    pid, _ = _seed(client)
    create_r = client.post("/api/story-milestones", json={
        "project_id": pid, "title": "X",
    })
    rid = create_r.json()["id"]
    r = client.patch(f"/api/story-milestones/{rid}", json={
        "status": "done", "title": "完成",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    assert r.json()["title"] == "完成"


def test_delete(client):
    pid, _ = _seed(client)
    create_r = client.post("/api/story-milestones", json={
        "project_id": pid, "title": "X",
    })
    rid = create_r.json()["id"]
    r = client.delete(f"/api/story-milestones/{rid}")
    assert r.status_code == 204
    assert client.get(f"/api/story-milestones?project_id={pid}").json() == []


def test_list_requires_project_id(client):
    r = client.get("/api/story-milestones")
    assert r.status_code == 422
