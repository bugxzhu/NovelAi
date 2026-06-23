"""Genre templates tests."""
from app.config.genre_templates import GENRE_TEMPLATES, get_genre_template, get_genre_templates_for_api


REQUIRED_FIELDS = {
    "label", "description", "world_defaults", "writer_guidance",
    "reviewer_criteria", "extractor_hints",
    "character_archetypes", "plot_templates",
}


def test_all_templates_have_required_fields():
    assert len(GENRE_TEMPLATES) == 10
    for key, tpl in GENRE_TEMPLATES.items():
        missing = REQUIRED_FIELDS - set(tpl.keys())
        assert not missing, f"{key} missing fields: {missing}"
        assert isinstance(tpl["character_archetypes"], list)
        assert len(tpl["character_archetypes"]) > 0
        assert isinstance(tpl["plot_templates"], list)
        assert len(tpl["plot_templates"]) > 0
        assert "power_system" in tpl["world_defaults"]
        assert "rules_and_taboos" in tpl["world_defaults"]


def test_get_genre_template_known():
    tpl = get_genre_template("xuanhuan")
    assert tpl is not None
    assert tpl["label"] == "玄幻"


def test_get_genre_template_unknown_returns_none():
    assert get_genre_template("自定义类型") is None
    assert get_genre_template("") is None


def test_get_genre_templates_for_api_excludes_backend_fields():
    data = get_genre_templates_for_api()
    assert len(data) == 10
    for key, tpl in data.items():
        assert "reviewer_criteria" not in tpl
        assert "extractor_hints" not in tpl
        assert "writer_guidance" not in tpl
        assert "label" in tpl
        assert "world_defaults" in tpl


def test_genre_templates_api_endpoint(client):
    r = client.get("/api/genre-templates")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 10
    assert "xuanhuan" in data
    assert data["xuanhuan"]["label"] == "玄幻"
