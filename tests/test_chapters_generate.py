import json

import pytest

from app.llm.streaming import StreamEvent


@pytest.fixture
def fake_router(monkeypatch):
    """Patch default_router at the endpoint module to yield a fixed stream."""
    class _Fake:
        def resolve_model(self, task):
            return ("claude", "claude-sonnet-4-6")
        def stream(self, request):
            yield StreamEvent(type="token", text="Hello ")
            yield StreamEvent(type="token", text="world")
            yield StreamEvent(type="done", input_tokens=10, output_tokens=2,
                              stop_reason="end_turn")
    fake = _Fake()
    monkeypatch.setattr("app.api.chapters_generate.default_router", fake)
    return fake


def _seed(client):
    pid = client.post("/api/projects", json={"title": "P"}).json()["id"]
    client.put(f"/api/projects/{pid}/world-overview",
               json={"setting_era": "Medieval"}).json()
    c1 = client.post("/api/characters",
                     json={"project_id": pid, "name": "C1"}).json()["id"]
    c2 = client.post("/api/characters",
                     json={"project_id": pid, "name": "C2"}).json()["id"]
    loc = client.post("/api/lore",
                      json={"project_id": pid, "type": "location",
                            "name": "Loc"}).json()["id"]
    ch = client.post("/api/chapters",
                     json={"project_id": pid, "order_index": 1,
                           "title": "CH"}).json()["id"]
    return pid, [c1, c2], loc, ch


def _parse_sse(lines):
    """Parse SSE chunks from iter_lines. Returns list of (event, data_dict)."""
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


def test_generate_returns_404_unknown_chapter(client, fake_router):
    r = client.post("/api/chapters/99999/generate",
                    json={"beat_text": "x", "involved_character_ids": [1]})
    assert r.status_code == 404
    assert r.json()["detail"] == "chapter not found"


def test_generate_returns_422_invalid_character_id(client, fake_router):
    pid, chars, loc, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/generate",
                    json={"beat_text": "x",
                          "involved_character_ids": [99999]})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "invalid_context"
    assert 99999 in detail["invalid_character_ids"]


def test_generate_returns_422_invalid_location_id(client, fake_router):
    pid, chars, loc, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/generate",
                    json={"beat_text": "x",
                          "involved_character_ids": [chars[0]],
                          "location_id": 99999})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "invalid_context"
    assert detail["invalid_location_id"] == 99999


def test_generate_returns_422_too_many_chars(client, fake_router):
    pid, chars, loc, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/generate",
                    json={"beat_text": "x",
                          "involved_character_ids": list(range(21))})
    assert r.status_code == 422


def test_generate_returns_422_empty_beat(client, fake_router):
    pid, chars, loc, ch = _seed(client)
    r = client.post(f"/api/chapters/{ch}/generate",
                    json={"beat_text": "",
                          "involved_character_ids": [chars[0]]})
    assert r.status_code == 422


def test_generate_sse_full_sequence(client, fake_router):
    pid, chars, loc, ch = _seed(client)
    with client.stream("POST", f"/api/chapters/{ch}/generate",
                       json={"beat_text": "主角遇旧友",
                             "instruction": "压抑",
                             "involved_character_ids": chars,
                             "location_id": loc}) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        events = _parse_sse(response.iter_lines())
    types = [e for e, _ in events]
    assert types == ["meta", "context", "token", "token", "done"]
    meta = events[0][1]
    assert meta["model"] == "claude-sonnet-4-6"
    log_id = meta["generation_log_id"]
    context = events[1][1]["context_bundle"]
    assert context["world_overview"]["setting_era"] == "Medieval"
    assert any(c["name"] == "C1" for c in context["characters"])
    token_text = "".join(d["text"] for e, d in events if e == "token")
    assert token_text == "Hello world"
    done = events[-1][1]
    assert done["generation_log_id"] == log_id
    assert done["input_tokens"] == 10
    assert done["stop_reason"] == "end_turn"


def test_generate_sse_emits_error_event_on_llm_failure(client, monkeypatch):
    class _ErrRouter:
        def resolve_model(self, task):
            return ("claude", "claude-sonnet-4-6")
        def stream(self, request):
            yield StreamEvent(type="token", text="partial")
            yield StreamEvent(type="error", error_message="API dead",
                              error_code="RuntimeError")
    monkeypatch.setattr("app.api.chapters_generate.default_router", _ErrRouter())
    pid, chars, loc, ch = _seed(client)
    with client.stream("POST", f"/api/chapters/{ch}/generate",
                       json={"beat_text": "x",
                             "involved_character_ids": [chars[0]]}) as response:
        events = _parse_sse(response.iter_lines())
    types = [e for e, _ in events]
    assert types == ["meta", "context", "token", "error"]
    err = events[-1][1]
    assert "API dead" in err["message"]
    assert err["code"] == "RuntimeError"
    log_id = events[0][1]["generation_log_id"]
    # DB log marked failed — verify via DB (Task 7 detail endpoint comes later)
    from app.memory.schema import GenerationLog
    from sqlalchemy import create_engine, select
    # Use the same DB the test client is bound to via app state
    # Simpler: query via the API by listing logs (Task 7 not yet implemented)
    # For now, just check the event sequence and error payload
    assert log_id > 0


def test_generate_creates_log_before_streaming(client, fake_router):
    """Meta event must include a generation_log_id (positive int)."""
    pid, chars, loc, ch = _seed(client)
    with client.stream("POST", f"/api/chapters/{ch}/generate",
                       json={"beat_text": "x",
                             "involved_character_ids": [chars[0]]}) as response:
        events = _parse_sse(response.iter_lines())
    meta = events[0][1]
    log_id = meta["generation_log_id"]
    assert isinstance(log_id, int)
    assert log_id > 0
