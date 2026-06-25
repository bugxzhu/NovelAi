"""Tests for chapter version history endpoints.

Covers:
  POST   /api/chapters/{chapter_id}/versions
  GET    /api/chapters/{chapter_id}/versions
  GET    /api/chapter-versions/{version_id}
  POST   /api/chapter-versions/{version_id}/restore

Plus cascade verification through the chapter delete path.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app  # noqa: F401  (ensures import side-effects happen)


@pytest.fixture
def chapter_id(client: TestClient):
    """Create a project + chapter for testing. Returns chapter_id."""
    proj = client.post("/api/projects", json={"title": "T"}).json()
    ch = client.post(
        "/api/chapters",
        json={"project_id": proj["id"], "order_index": 1, "title": "C1", "content": ""},
    ).json()
    return ch["id"]


class TestCreateVersion:
    def test_create_manual(self, client: TestClient, chapter_id: int):
        r = client.post(
            f"/api/chapters/{chapter_id}/versions",
            json={"content": "hello world", "reason": "manual"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["chapter_id"] == chapter_id
        assert body["reason"] == "manual"
        assert body["char_count"] == 11
        assert "content" not in body  # response omits content

    def test_create_invalid_reason(self, client: TestClient, chapter_id: int):
        r = client.post(
            f"/api/chapters/{chapter_id}/versions",
            json={"content": "x", "reason": "bogus"},
        )
        assert r.status_code == 422

    def test_create_unknown_chapter(self, client: TestClient):
        r = client.post(
            "/api/chapters/99999/versions",
            json={"content": "x", "reason": "manual"},
        )
        assert r.status_code == 404


class TestListVersions:
    def test_list_excludes_content(self, client: TestClient, chapter_id: int):
        client.post(f"/api/chapters/{chapter_id}/versions",
                    json={"content": "first", "reason": "manual"})
        client.post(f"/api/chapters/{chapter_id}/versions",
                    json={"content": "second", "reason": "manual"})
        r = client.get(f"/api/chapters/{chapter_id}/versions")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 2
        assert "content" not in items[0]
        # Newest first
        assert items[0]["char_count"] == 6  # "second"
        assert items[1]["char_count"] == 5  # "first"

    def test_list_delta_char_count(self, client: TestClient, chapter_id: int):
        # Set chapter content to "bye" (3 chars)
        client.patch(f"/api/chapters/{chapter_id}", json={"content": "bye"})
        # Snapshot with 10 chars
        client.post(f"/api/chapters/{chapter_id}/versions",
                    json={"content": "0123456789", "reason": "manual"})
        # Snapshot with 5 chars
        client.post(f"/api/chapters/{chapter_id}/versions",
                    json={"content": "01234", "reason": "manual"})
        r = client.get(f"/api/chapters/{chapter_id}/versions")
        items = r.json()
        # Newest (5 chars): delta vs current chapter ("bye"=3) = -2
        assert items[0]["delta_char_count"] == -2
        # Older (10 chars): delta vs newer sibling (5) = -5
        assert items[1]["delta_char_count"] == -5

    def test_list_empty(self, client: TestClient, chapter_id: int):
        r = client.get(f"/api/chapters/{chapter_id}/versions")
        assert r.status_code == 200
        assert r.json() == []


class TestGetVersion:
    def test_get_includes_content(self, client: TestClient, chapter_id: int):
        create = client.post(
            f"/api/chapters/{chapter_id}/versions",
            json={"content": "full body", "reason": "manual"},
        ).json()
        r = client.get(f"/api/chapter-versions/{create['id']}")
        assert r.status_code == 200
        body = r.json()
        assert body["content"] == "full body"
        assert body["id"] == create["id"]

    def test_get_missing(self, client: TestClient):
        r = client.get("/api/chapter-versions/99999")
        assert r.status_code == 404


class TestRestore:
    def test_restore_transactional(self, client: TestClient, chapter_id: int):
        # chapter.content starts empty; set to "original"
        client.patch(f"/api/chapters/{chapter_id}", json={"content": "original"})
        # Snapshot with "older" content
        snap = client.post(
            f"/api/chapters/{chapter_id}/versions",
            json={"content": "older", "reason": "manual"},
        ).json()
        # Restore
        r = client.post(f"/api/chapter-versions/{snap['id']}/restore")
        assert r.status_code == 200
        body = r.json()
        assert body["restored_version_id"] == snap["id"]
        assert "new_pre_restore_id" in body
        # Verify chapter.content is now "older"
        ch = client.get(f"/api/chapters/{chapter_id}").json()
        assert ch["content"] == "older"
        # Verify pre_restore row was created with "original"
        pre = client.get(f"/api/chapter-versions/{body['new_pre_restore_id']}").json()
        assert pre["content"] == "original"
        assert pre["reason"] == "pre_restore"

    def test_restore_missing(self, client: TestClient):
        r = client.post("/api/chapter-versions/99999/restore")
        assert r.status_code == 404


class TestCascade:
    def test_delete_chapter_cascades(self, client: TestClient, chapter_id: int):
        snap = client.post(
            f"/api/chapters/{chapter_id}/versions",
            json={"content": "x", "reason": "manual"},
        ).json()
        client.delete(f"/api/chapters/{chapter_id}")
        r = client.get(f"/api/chapter-versions/{snap['id']}")
        assert r.status_code == 404
