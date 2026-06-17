import pytest

from app.models.chapter import ChapterCreate, ChapterRead, ChapterUpdate


def test_chapter_create_has_project_id():
    c = ChapterCreate(project_id=1)
    assert c.project_id == 1


def test_chapter_read_includes_default_set_fields():
    """ChapterRead must expose last_involved_character_ids and last_location_id."""
    fields = ChapterRead.model_fields
    assert "last_involved_character_ids" in fields
    assert "last_location_id" in fields


def test_chapter_update_allows_default_set_patch():
    fields = ChapterUpdate.model_fields
    assert "last_involved_character_ids" in fields
    assert "last_location_id" in fields
