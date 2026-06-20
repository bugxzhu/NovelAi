import pytest

from app.llm.streaming import StreamEvent


@pytest.fixture
def fake_router(monkeypatch):
    class _Fake:
        def resolve_model(self, task):
            return ("claude", "claude-sonnet-4-6")
        def stream(self, request):
            yield StreamEvent(type="token", text="Hi")
            yield StreamEvent(type="done", input_tokens=10, output_tokens=2,
                              stop_reason="end_turn")
        def embed(self, texts, model=None):
            return [[0.1] * 1024] * len(texts)
    fake = _Fake()
    monkeypatch.setattr("app.api.chapters_generate.default_router", fake)
    return fake


def _seed_two_chapters_with_logs(client, fake_router):
    """Create project + 2 chapters, generate once for each."""
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    c1 = client.post("/api/characters",
                     json={"project_id": pid, "name": "C1"}).json()["id"]
    ch1 = client.post("/api/chapters",
                      json={"project_id": pid, "order_index": 1,
                            "title": "CH1"}).json()["id"]
    ch2 = client.post("/api/chapters",
                      json={"project_id": pid, "order_index": 2,
                            "title": "CH2"}).json()["id"]
    # Generate for ch1
    with client.stream("POST", f"/api/chapters/{ch1}/generate",
                       json={"beat_text": "b1",
                             "involved_character_ids": [c1]}) as r:
        assert r.status_code == 200
    # Generate for ch2
    with client.stream("POST", f"/api/chapters/{ch2}/generate",
                       json={"beat_text": "b2",
                             "involved_character_ids": [c1]}) as r:
        assert r.status_code == 200
    return pid, ch1, ch2


def test_list_requires_chapter_or_project_id(client):
    """Neither param -> 422."""
    r = client.get("/api/generation-logs")
    assert r.status_code == 422


def test_list_with_project_id_returns_all_project_logs(client, fake_router):
    """list endpoint accepts project_id and returns all logs in that project."""
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    c1 = client.post("/api/characters",
                     json={"project_id": pid, "name": "C1"}).json()["id"]
    ch1 = client.post("/api/chapters",
                      json={"project_id": pid, "order_index": 1,
                            "title": "CH1"}).json()["id"]
    ch2 = client.post("/api/chapters",
                      json={"project_id": pid, "order_index": 2,
                            "title": "CH2"}).json()["id"]
    # Generate once per chapter
    for ch in (ch1, ch2):
        with client.stream("POST", f"/api/chapters/{ch}/generate",
                           json={"beat_text": "x",
                                 "involved_character_ids": [c1]}) as r:
            assert r.status_code == 200

    r = client.get(f"/api/generation-logs?project_id={pid}")
    assert r.status_code == 200
    logs = r.json()
    assert len(logs) == 2
    assert {log["chapter_id"] for log in logs} == {ch1, ch2}


def test_list_returns_only_target_chapter(client, fake_router):
    pid, ch1, ch2 = _seed_two_chapters_with_logs(client, fake_router)
    r = client.get(f"/api/generation-logs?chapter_id={ch1}")
    assert r.status_code == 200
    logs = r.json()
    assert len(logs) == 1
    assert logs[0]["chapter_id"] == ch1
    assert logs[0]["status"] == "done"


def test_list_pagination(client, fake_router):
    pid, ch1, ch2 = _seed_two_chapters_with_logs(client, fake_router)
    # Generate 3 more for ch1 to test pagination
    c1 = client.get(f"/api/characters?project_id={pid}").json()[0]["id"]
    for _ in range(3):
        with client.stream("POST", f"/api/chapters/{ch1}/generate",
                           json={"beat_text": "x",
                                 "involved_character_ids": [c1]}) as r:
            assert r.status_code == 200
    r = client.get(f"/api/generation-logs?chapter_id={ch1}&limit=2")
    assert len(r.json()) == 2
    r = client.get(f"/api/generation-logs?chapter_id={ch1}&limit=2&offset=2")
    assert len(r.json()) == 2
    r = client.get(f"/api/generation-logs?chapter_id={ch1}&limit=100&offset=0")
    assert len(r.json()) == 4


def test_detail_returns_full_prompt(client, fake_router):
    pid, ch1, _ = _seed_two_chapters_with_logs(client, fake_router)
    log_id = client.get(f"/api/generation-logs?chapter_id={ch1}").json()[0]["id"]
    r = client.get(f"/api/generation-logs/{log_id}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["id"] == log_id
    assert "system_prompt" in detail
    assert "user_prompt" in detail
    assert "P" in detail["user_prompt"]
    assert detail["generated_text"] == "Hi"
    assert detail["input_tokens"] == 10


def test_detail_404(client):
    r = client.get("/api/generation-logs/99999")
    assert r.status_code == 404
    assert r.json()["detail"] == "generation log not found"
