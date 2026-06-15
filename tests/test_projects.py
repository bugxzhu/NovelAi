def test_create_project(client):
    r = client.post("/api/projects", json={"title": "My Novel", "genre": "fantasy"})
    assert r.status_code == 201
    data = r.json()
    assert data["id"] > 0
    assert data["title"] == "My Novel"
    assert data["genre"] == "fantasy"


def test_list_projects(client):
    client.post("/api/projects", json={"title": "A"})
    client.post("/api/projects", json={"title": "B"})
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_project(client):
    r = client.post("/api/projects", json={"title": "X"})
    pid = r.json()["id"]
    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 200
    assert r.json()["title"] == "X"


def test_get_project_not_found(client):
    r = client.get("/api/projects/9999")
    assert r.status_code == 404


def test_update_project(client):
    r = client.post("/api/projects", json={"title": "Old"})
    pid = r.json()["id"]
    r = client.patch(f"/api/projects/{pid}", json={"title": "New"})
    assert r.status_code == 200
    assert r.json()["title"] == "New"


def test_delete_project(client):
    r = client.post("/api/projects", json={"title": "X"})
    pid = r.json()["id"]
    r = client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404
