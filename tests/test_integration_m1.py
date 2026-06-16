def test_full_m1_workflow(client):
    # 1. 建项目
    pid = client.post(
        "/api/projects", json={"title": "Demo", "genre": "fantasy"}
    ).json()["id"]

    # 2. 写世界观
    wo = client.put(
        f"/api/projects/{pid}/world-overview",
        json={"setting_era": "中古", "power_system": "魔法"},
    ).json()
    assert wo["project_id"] == pid

    # 3. 建 lore：王国 -> 城市
    kingdom = client.post(
        "/api/lore",
        json={"project_id": pid, "type": "location", "name": "王国"},
    ).json()["id"]
    city = client.post(
        "/api/lore",
        json={"project_id": pid, "type": "location", "name": "王城", "parent_id": kingdom},
    ).json()["id"]

    # 4. 建势力
    faction = client.post(
        "/api/lore",
        json={"project_id": pid, "type": "faction", "name": "守夜人"},
    ).json()["id"]

    # 5. 建人物（关联 lore）
    char = client.post(
        "/api/characters",
        json={
            "project_id": pid,
            "name": "李雷",
            "role": "主角",
            "affiliations": [faction],
            "known_locations": [city],
        },
    ).json()
    assert char["affiliations"] == [faction]

    # 6. 建章节
    ch = client.post(
        "/api/chapters",
        json={
            "project_id": pid,
            "order_index": 1,
            "title": "第一章",
            "outline": "主角在王城遇守夜人",
        },
    ).json()
    assert ch["status"] == "draft"

    # 7. 列表查询
    assert len(client.get(f"/api/lore?project_id={pid}").json()) == 3
    assert len(client.get(f"/api/characters?project_id={pid}").json()) == 1
    assert len(client.get(f"/api/chapters?project_id={pid}").json()) == 1

    # 8. 删除项目级联清理
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/lore?project_id={pid}").json() == []
    assert client.get(f"/api/characters?project_id={pid}").json() == []
