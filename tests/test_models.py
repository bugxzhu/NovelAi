from datetime import UTC, datetime

from app.models.project import ProjectCreate, ProjectRead


def test_project_create_minimal():
    p = ProjectCreate(title="My Novel")
    assert p.title == "My Novel"
    assert p.genre == ""
    assert p.premise == ""


def test_project_read_includes_id_and_timestamps():
    p = ProjectRead(
        id=1, title="X", genre="", premise="", main_theme="", tone="",
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    assert p.id == 1
