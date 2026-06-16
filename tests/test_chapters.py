def _make_project(client):
    return client.post("/api/projects", json={"title": "X"}).json()["id"]


def test_create_chapter(client):
    pid = _make_project(client)
    r = client.post(
        "/api/chapters",
        json={
            "project_id": pid,
            "order_index": 1,
            "title": "第一章",
            "outline": "主角离家",
        },
    )
    assert r.status_code == 201
    assert r.json()["title"] == "第一章"
    assert r.json()["status"] == "draft"


def test_list_chapters_ordered(client):
    pid = _make_project(client)
    client.post("/api/chapters", json={"project_id": pid, "order_index": 2, "title": "B"})
    client.post("/api/chapters", json={"project_id": pid, "order_index": 1, "title": "A"})
    r = client.get(f"/api/chapters?project_id={pid}")
    assert [c["title"] for c in r.json()] == ["A", "B"]


def test_update_chapter_content(client):
    pid = _make_project(client)
    cid = client.post(
        "/api/chapters", json={"project_id": pid, "order_index": 1, "title": "T"}
    ).json()["id"]
    r = client.patch(
        f"/api/chapters/{cid}",
        json={"content": "主角推开门，看见...", "status": "writing"},
    )
    assert r.status_code == 200
    assert r.json()["content"].startswith("主角推开门")
    assert r.json()["status"] == "writing"


def test_delete_chapter(client):
    pid = _make_project(client)
    cid = client.post(
        "/api/chapters", json={"project_id": pid, "order_index": 1, "title": "T"}
    ).json()["id"]
    assert client.delete(f"/api/chapters/{cid}").status_code == 204


def test_create_chapter_with_invalid_project_returns_404(client):
    r = client.post(
        "/api/chapters",
        json={"project_id": 99999, "order_index": 1, "title": "T"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "project not found"
