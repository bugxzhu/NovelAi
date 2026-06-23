from types import SimpleNamespace

import pytest
from jinja2 import UndefinedError

from app.llm.prompts import render


def _fake_project():
    return SimpleNamespace(
        title="TestNovel", genre="fantasy", main_theme="courage",
        tone="epic", premise="A test premise.",
    )


def _fake_world_overview():
    return SimpleNamespace(
        setting_era="Medieval", geography_summary="Many islands",
        history_summary="Old war", culture_summary="Multi-ethnic",
        power_system="Magic", rules_and_taboos="No necromancy",
    )


def _fake_character(id_=1, name="Li", role="protagonist"):
    return SimpleNamespace(
        id=id_, name=name, role=role,
        personality={"mbti": "INTJ", "traits": ["calm"]},
        speech_style="short sentences",
        motivation="revenge",
        background="orphan",
    )


def _fake_state(state="angry"):
    return SimpleNamespace(current_state=state, change_summary="")


def _fake_summary(title="Prev", order_index=1, summary="stuff"):
    return SimpleNamespace(chapter_id=10, order_index=order_index,
                            title=title, summary=summary)


def _fake_lore(name="Loc1", type_="location", description="A place."):
    return SimpleNamespace(name=name, type=type_, description=description,
                            title="", parent_id=None)


def test_render_system_returns_nonempty():
    out = render("writer/system.j2")
    assert isinstance(out, str)
    assert "小说写作助手" in out or "novel" in out.lower()


def test_render_user_full():
    out = render(
        "writer/user.j2",
        project=_fake_project(),
        world_overview=_fake_world_overview(),
        characters=[_fake_character()],
        character_states={1: _fake_state()},
        relationships=[],
        faction_lore=[_fake_lore(name="守夜人", type_="faction")],
        location_lore=[_fake_lore()],
        plot_lines=[],
        recent_chapter_summaries=[_fake_summary()],
        beat_text="主角遇旧友",
        instruction="氛围压抑",
        retrieved_chunks=[],
        milestones=[],
        genre_template=None,
    )
    assert "TestNovel" in out
    assert "Medieval" in out
    assert "Li" in out
    assert "守夜人" in out
    assert "主角遇旧友" in out
    assert "氛围压抑" in out


def test_render_user_minimal_no_world_no_lore_no_recent():
    out = render(
        "writer/user.j2",
        project=_fake_project(),
        world_overview=None,
        characters=[_fake_character()],
        character_states={1: _fake_state()},
        relationships=[],
        faction_lore=[],
        location_lore=[],
        plot_lines=[],
        recent_chapter_summaries=[],
        beat_text="x",
        instruction="",
        retrieved_chunks=[],
        milestones=[],
        genre_template=None,
    )
    assert "TestNovel" in out
    assert "Li" in out
    assert "x" in out
    assert "Medieval" not in out


def test_render_user_missing_variable_raises():
    with pytest.raises(UndefinedError):
        render("writer/user.j2", project=_fake_project())


def test_render_user_empty_characters_list():
    out = render(
        "writer/user.j2",
        project=_fake_project(),
        world_overview=None,
        characters=[],
        character_states={},
        relationships=[],
        faction_lore=[],
        location_lore=[],
        plot_lines=[],
        recent_chapter_summaries=[],
        beat_text="x",
        instruction="",
        retrieved_chunks=[],
        milestones=[],
        genre_template=None,
    )
    assert "TestNovel" in out
    assert "x" in out


def test_render_writer_user_has_plot_lines():
    """writer/user.j2 renders plot_lines section."""
    from types import SimpleNamespace
    pl = SimpleNamespace(type="main", title="复仇之路", summary="在推进")
    out = render("writer/user.j2",
                 project=SimpleNamespace(title="T", genre="g", main_theme="m",
                                         tone="t", premise="p"),
                 world_overview=None,
                 characters=[],
                 character_states={},
                 relationships=[],
                 lore_entries=[],
                 faction_lore=[],
                 location_lore=[],
                 plot_lines=[pl],
                 recent_chapter_summaries=[],
                 retrieved_chunks=[],
                 beat_text="x",
                 instruction="",
                 milestones=[],
                 genre_template=None)
    assert "当前情节线" in out
    assert "复仇之路" in out


def test_render_writer_user_has_milestones():
    """writer/user.j2 renders milestones section."""
    from types import SimpleNamespace
    m = SimpleNamespace(status="planned", title="真相揭示", type="转折",
                        chapter_start=5, chapter_end=7, description="关键转折")
    out = render("writer/user.j2",
                 project=SimpleNamespace(title="T", genre="g", main_theme="m",
                                         tone="t", premise="p"),
                 world_overview=None,
                 characters=[], character_states={}, relationships=[],
                 lore_entries=[], faction_lore=[], location_lore=[],
                 plot_lines=[],
                 milestones=[m],
                 recent_chapter_summaries=[], retrieved_chunks=[],
                 beat_text="x", instruction="",
                 genre_template=None)
    assert "故事蓝图" in out
    assert "真相揭示" in out
