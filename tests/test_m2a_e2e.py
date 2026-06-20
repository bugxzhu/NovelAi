import json


def _parse_sse(lines):
    events = []
    current_event = None
    current_data = []
    for line in lines:
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: "):
            current_data.append(line[6:])
        elif line == "":
            if current_event and current_data:
                events.append((current_event, json.loads("".join(current_data))))
            current_event = None
            current_data = []
    return events


def test_full_m2a_workflow(client, monkeypatch):
    """End-to-end: seed → generate via SSE → verify DB log → verify prompts."""
    from app.llm.streaming import StreamEvent

    class _Fake:
        def resolve_model(self, task):
            return ("claude", "claude-sonnet-4-6")
        def stream(self, request):
            yield StreamEvent(type="token", text="夜色压在屋脊上，")
            yield StreamEvent(type="token", text="李雷推开了酒馆的门。")
            yield StreamEvent(type="done", input_tokens=3200, output_tokens=850,
                              stop_reason="end_turn")
        def embed(self, texts, model=None):
            return [[0.1] * 1024] * len(texts)
    monkeypatch.setattr("app.api.chapters_generate.default_router", _Fake())

    # Seed project + world + chars + lore + 1 prior chapter with summary
    pid = client.post("/api/projects", json={
        "title": "夜行记", "genre": "fantasy", "premise": "主角寻仇",
        "main_theme": "复仇", "tone": "压抑",
    }).json()["id"]
    client.put(f"/api/projects/{pid}/world-overview", json={
        "setting_era": "中古", "power_system": "剑与魔法",
        "rules_and_taboos": "魔法消耗寿命",
    }).json()
    kingdom = client.post("/api/lore", json={
        "project_id": pid, "type": "location", "name": "青石王国",
        "description": "北方小国",
    }).json()["id"]
    city = client.post("/api/lore", json={
        "project_id": pid, "type": "location", "name": "青石城",
        "description": "王国首都", "parent_id": kingdom,
    }).json()["id"]
    faction = client.post("/api/lore", json={
        "project_id": pid, "type": "faction", "name": "守夜人",
        "description": "情报组织",
    }).json()["id"]
    c1 = client.post("/api/characters", json={
        "project_id": pid, "name": "李雷", "role": "主角",
        "personality": {"mbti": "INTJ", "traits": ["冷静", "固执"]},
        "speech_style": "短句，常引古文",
        "background": "孤儿", "motivation": "复仇",
        "current_state": "刚进城",
        "affiliations": [faction], "known_locations": [city],
    }).json()["id"]
    c2 = client.post("/api/characters", json={
        "project_id": pid, "name": "韩梅", "role": "旧友",
        "current_state": "在酒馆",
    }).json()["id"]
    prior = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "序幕",
        "summary": "李雷离家北上，进入青石王国。",
    }).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 2, "title": "第二章",
    }).json()["id"]

    # Trigger generation via SSE
    with client.stream("POST", f"/api/chapters/{ch}/generate",
                       json={
                           "beat_text": "主角在酒馆遇旧友",
                           "instruction": "氛围压抑",
                           "involved_character_ids": [c1, c2],
                           "location_id": city,
                           "model_task": "writer_long",
                           "max_tokens": 4096,
                       }) as response:
        assert response.status_code == 200
        events = _parse_sse(response.iter_lines())

    # Verify SSE event sequence
    types = [e for e, _ in events]
    assert types == ["meta", "context", "token", "token", "done"]
    meta = events[0][1]
    log_id = meta["generation_log_id"]
    assert meta["model"] == "claude-sonnet-4-6"

    # Verify context event contains assembled常驻层
    context = events[1][1]["context_bundle"]
    assert context["project"]["title"] == "夜行记"
    assert context["world_overview"]["power_system"] == "剑与魔法"
    char_names = {c["name"] for c in context["characters"]}
    assert char_names == {"李雷", "韩梅"}
    loc_names = {l["name"] for l in context["location_lore"]}
    assert loc_names == {"青石王国", "青石城"}  # ancestors included
    faction_names = {f["name"] for f in context["faction_lore"]}
    assert faction_names == {"守夜人"}
    assert any(s["title"] == "序幕" for s in context["recent_chapter_summaries"])

    # Verify token stream
    token_text = "".join(d["text"] for e, d in events if e == "token")
    assert "夜色压在屋脊上" in token_text
    assert "李雷推开了酒馆的门" in token_text

    # Verify DB log via detail endpoint
    detail = client.get(f"/api/generation-logs/{log_id}").json()
    assert detail["status"] == "done"
    assert detail["input_tokens"] == 3200
    assert detail["output_tokens"] == 850
    assert detail["stop_reason"] == "end_turn"
    assert detail["generated_text"] == token_text
    # 验收核心：user_prompt 里有常驻层关键词
    assert "李雷" in detail["user_prompt"]
    assert "韩梅" in detail["user_prompt"]
    assert "青石城" in detail["user_prompt"]
    assert "守夜人" in detail["user_prompt"]
    assert "剑与魔法" in detail["user_prompt"]
    assert "复仇" in detail["user_prompt"]  # main_theme
    assert "序幕" in detail["user_prompt"]  # recent summary


def test_invalid_character_returns_422_with_detail(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    ch = client.post("/api/chapters", json={
        "project_id": pid, "order_index": 1, "title": "C",
    }).json()["id"]
    r = client.post(f"/api/chapters/{ch}/generate", json={
        "beat_text": "x", "involved_character_ids": [99999],
    })
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "invalid_context"
    assert detail["invalid_character_ids"] == [99999]
