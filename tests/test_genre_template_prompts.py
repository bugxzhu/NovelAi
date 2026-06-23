"""Genre template injection into agent prompts (Writer/Reviewer/Extractor/Discuss/Polish)."""
from types import SimpleNamespace

from app.config.genre_templates import get_genre_template
from app.llm.prompts import render


def _stub_project(genre="xuanhuan"):
    return SimpleNamespace(
        title="T", genre=genre, main_theme="m", tone="t", premise="p",
    )


def test_render_writer_user_has_genre_guidance():
    gt = get_genre_template("xuanhuan")
    out = render(
        "writer/user.j2",
        project=_stub_project(),
        world_overview=None,
        characters=[], character_states={}, relationships=[],
        faction_lore=[], location_lore=[], plot_lines=[], milestones=[],
        recent_chapter_summaries=[], retrieved_chunks=[],
        beat_text="x", instruction="",
        genre_template=gt,
    )
    assert "类型创作指导" in out
    assert "玄幻" in out  # xuanhuan label
    # writer_guidance content is included
    assert "境界" in out


def test_render_reviewer_user_has_genre_criteria():
    gt = get_genre_template("xuanhuan")
    out = render(
        "reviewer/user.j2",
        project=_stub_project(),
        world_overview=None,
        chapter=SimpleNamespace(order_index=1, title="C1", content="正文"),
        characters=[], character_states_history={},
        relationships=[], events=[], lore_entries=[],
        plot_lines=[], milestones=[],
        recent_chapter_summaries=[],
        genre_template=gt,
    )
    assert "类型审稿标准" in out
    assert "玄幻" in out
    # reviewer_criteria content included
    assert "力量体系" in out


def test_render_extractor_user_has_genre_hints():
    gt = get_genre_template("xuanhuan")
    out = render(
        "extractor/user.j2",
        project=_stub_project(),
        chapter=SimpleNamespace(title="C1", content="正文", order_index=1),
        existing_characters=[], existing_lore=[],
        existing_relationships=[], rejected_suggestions=[],
        genre_template=gt,
    )
    assert "类型抽取提示" in out
    assert "玄幻" in out
    # extractor_hints content included
    assert "境界" in out


def test_render_discuss_user_has_genre_guidance():
    gt = get_genre_template("xianxia")
    out = render(
        "discuss/user.j2",
        project=_stub_project(genre="xianxia"),
        world_overview=None,
        chapter=SimpleNamespace(order_index=1, title="C1", content="正文"),
        characters=[], character_states_history={},
        relationships=[], events=[], lore_entries=[],
        plot_lines=[], milestones=[],
        recent_chapter_summaries=[],
        question="如果？",
        selected_text="",
        genre_template=gt,
    )
    assert "类型创作指导" in out
    assert "仙侠" in out


def test_render_polish_user_has_genre_guidance():
    gt = get_genre_template("wuxia")
    out = render(
        "polish/user.j2",
        project=_stub_project(genre="wuxia"),
        world_overview=None,
        characters=[], character_states={}, relationships=[],
        plot_lines=[], milestones=[],
        selected_text="",
        chapter_content="待润色正文。",
        direction="",
        is_selection=False,
        genre_template=gt,
    )
    assert "类型创作指导" in out
    assert "武侠" in out


def test_genre_template_none_omits_section():
    """When genre_template is None (custom genre), no section is rendered."""
    out = render(
        "writer/user.j2",
        project=_stub_project(),
        world_overview=None,
        characters=[], character_states={}, relationships=[],
        faction_lore=[], location_lore=[], plot_lines=[], milestones=[],
        recent_chapter_summaries=[], retrieved_chunks=[],
        beat_text="x", instruction="",
        genre_template=None,
    )
    assert "类型创作指导" not in out
