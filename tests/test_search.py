"""Tests for /api/search full-text search endpoint."""


def test_search_chapters(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "残月酒馆",
        "content": "李雷推开残月酒馆的门，遇见韩梅。"
    }).json()["id"]
    r = client.get(f"/api/search?project_id={pid}&q=残月酒馆")
    assert r.status_code == 200
    data = r.json()
    assert len(data["chapters"]) == 1
    assert "残月" in data["chapters"][0]["snippet"]


def test_search_characters(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    client.post("/api/characters", json={
        "project_id": pid, "name": "李雷", "background": "复仇者"
    })
    r = client.get(f"/api/search?project_id={pid}&q=复仇")
    assert len(r.json()["characters"]) == 1


def test_search_no_results(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    r = client.get(f"/api/search?project_id={pid}&q=不存在的内容")
    data = r.json()
    assert data["chapters"] == []
    assert data["characters"] == []


def test_search_requires_query(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    r = client.get(f"/api/search?project_id={pid}")
    assert r.status_code == 422


def test_search_lore_and_events(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "x"
    }).json()["id"]
    client.post("/api/lore", json={
        "project_id": pid, "type": "faction", "name": "暗影会", "description": "秘密组织"
    })
    client.post("/api/events", json={
        "project_id": pid, "chapter_id": ch, "title": "暗影降临", "description": "世界末日"
    })

    r = client.get(f"/api/search?project_id={pid}&q=暗影")
    data = r.json()
    assert len(data["lore"]) == 1
    assert data["lore"][0]["name"] == "暗影会"
    assert len(data["events"]) == 1
    assert data["events"][0]["name"] == "暗影降临"
