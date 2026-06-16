def _make_project(client):
    return client.post("/api/projects", json={"title": "X"}).json()["id"]


def test_create_character(client):
    pid = _make_project(client)
    r = client.post(
        "/api/characters",
        json={
            "project_id": pid,
            "name": "李雷",
            "role": "主角",
            "personality": {"mbti": "INTJ", "traits": ["冷静", "固执"]},
            "speech_style": "短句，常引古文",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "李雷"
    assert data["personality"]["mbti"] == "INTJ"
    assert data["speech_style"] == "短句，常引古文"


def test_list_characters_by_project(client):
    pid = _make_project(client)
    client.post("/api/characters", json={"project_id": pid, "name": "A"})
    client.post("/api/characters", json={"project_id": pid, "name": "B"})
    pid2 = _make_project(client)
    client.post("/api/characters", json={"project_id": pid2, "name": "C"})
    r = client.get(f"/api/characters?project_id={pid}")
    assert len(r.json()) == 2


def test_get_character_not_found(client):
    r = client.get("/api/characters/9999")
    assert r.status_code == 404


def test_update_character_partial(client):
    pid = _make_project(client)
    cid = client.post(
        "/api/characters", json={"project_id": pid, "name": "Old", "role": "配角"}
    ).json()["id"]
    r = client.patch(f"/api/characters/{cid}", json={"role": "主角"})
    assert r.status_code == 200
    assert r.json()["role"] == "主角"
    assert r.json()["name"] == "Old"


def test_delete_character(client):
    pid = _make_project(client)
    cid = client.post(
        "/api/characters", json={"project_id": pid, "name": "X"}
    ).json()["id"]
    assert client.delete(f"/api/characters/{cid}").status_code == 204
