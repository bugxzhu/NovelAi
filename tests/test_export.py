"""Tests for /api/projects/{id}/export endpoint."""


def test_export_markdown(client):
    pid = client.post("/api/projects", json={"title": "测试小说"}).json()["id"]
    client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "第一章",
        "content": "这是正文。"
    })
    r = client.get(f"/api/projects/{pid}/export?format=markdown")
    assert r.status_code == 200
    assert "测试小说" in r.text
    assert "第一章" in r.text
    assert "这是正文" in r.text


def test_export_txt(client):
    pid = client.post("/api/projects", json={"title": "T"}).json()["id"]
    client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C1", "content": "内容"
    })
    r = client.get(f"/api/projects/{pid}/export?format=txt")
    assert r.status_code == 200
    assert "内容" in r.text


def test_export_404(client):
    r = client.get("/api/projects/99999/export")
    assert r.status_code == 404


def test_export_orders_chapters(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    client.post("/api/chapters", json={
        "project_id": pid, "order_index": 2, "title": "B", "content": "b-content"
    })
    client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "A", "content": "a-content"
    })
    r = client.get(f"/api/projects/{pid}/export?format=markdown")
    assert r.status_code == 200
    a_idx = r.text.find("A")
    b_idx = r.text.find("B")
    assert a_idx >= 0 and b_idx >= 0
    assert a_idx < b_idx


def test_export_invalid_format(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    r = client.get(f"/api/projects/{pid}/export?format=pdf")
    assert r.status_code == 422
