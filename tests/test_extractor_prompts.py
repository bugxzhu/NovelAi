from types import SimpleNamespace

import pytest
from jinja2 import UndefinedError

from app.llm.prompts import render


def _fake_project():
    return SimpleNamespace(
        title="夜行记", genre="奇幻", premise="复仇故事",
        main_theme="复仇", tone="压抑",
    )


def _fake_chapter(content="夜色压在屋脊上。李雷推开残月酒馆的门。"):
    return SimpleNamespace(
        id=1, title="第二章", content=content,
    )


def _fake_character(id_=1, name="李雷", role="protagonist"):
    return SimpleNamespace(
        id=id_, name=name, role=role,
        background="南方孤儿", motivation="复仇",
        appearance="黑衣", current_state="愤怒",
    )


def _fake_lore(name="青石城", type_="location"):
    return SimpleNamespace(
        name=name, type=type_, description="王国首都",
    )


def test_render_system():
    out = render("extractor/system.j2")
    assert isinstance(out, str)
    assert "JSON" in out
    assert "summary" in out


def test_render_user_full():
    out = render(
        "extractor/user.j2",
        project=_fake_project(),
        chapter=_fake_chapter(),
        existing_characters=[_fake_character()],
        existing_lore=[_fake_lore()],
        existing_relationships=[],
        rejected_suggestions=[],
        genre_template=None,
    )
    assert "夜行记" in out
    assert "李雷" in out
    assert "青石城" in out
    assert "夜色压在屋脊上" in out


def test_render_user_minimal_no_entities():
    out = render(
        "extractor/user.j2",
        project=_fake_project(),
        chapter=_fake_chapter(),
        existing_characters=[],
        existing_lore=[],
        existing_relationships=[],
        rejected_suggestions=[],
        genre_template=None,
    )
    assert "夜行记" in out
    # Empty loops should not raise
    assert "已有人物（0" in out
    assert "已有设定（0" in out
    assert "已有关系（0" in out


def test_render_user_missing_var_raises():
    with pytest.raises(UndefinedError):
        render("extractor/user.j2", project=_fake_project())


from app.memory.schema import Character, Chapter, LoreEntry, Project


def _stub_project():
    return Project(title="T", genre="g", premise="p")


def _stub_chapter():
    return Chapter(project_id=1, order_index=3, title="第三章", content="正文...")


def test_system_prompt_has_state_changes_section():
    """system.j2 must document state_changes extraction rules."""
    out = render("extractor/system.j2")
    assert "state_changes" in out
    assert "情绪转变" in out or "情绪" in out
    assert "state_snapshot" in out
    assert "change_summary" in out


def test_system_prompt_removed_current_state_from_updated_characters():
    """current_state field changes must go through state_changes, not updated_characters."""
    out = render("extractor/system.j2")
    # Find the updated_characters field enum line
    assert "background|motivation|appearance" in out
    # The enum must NOT still list current_state as an updated_characters field
    # (it may still appear elsewhere — in the state_changes section — which is fine)
    # Find the updated_characters sample line and check it
    for line in out.splitlines():
        if "background|motivation|appearance" in line and "field" in line:
            assert "current_state" not in line, (
                f"updated_characters enum still lists current_state: {line!r}"
            )


def test_user_prompt_shows_current_state_for_existing_characters():
    """user.j2 must surface each existing character's current_state."""
    chars = [
        Character(id=1, project_id=1, name="李雷", role="protagonist",
                  background="bg", current_state="警惕"),
        Character(id=2, project_id=1, name="韩梅", role="supporting",
                  background="bg2", current_state=""),
    ]
    out = render("extractor/user.j2",
                 project=_stub_project(),
                 chapter=_stub_chapter(),
                 existing_characters=chars,
                 existing_lore=[],
                 existing_relationships=[],
                 rejected_suggestions=[],
                 genre_template=None)
    assert "现状=警惕" in out
    assert "现状=(未记录)" in out  # empty current_state placeholder


def test_system_prompt_has_relationship_changes_section():
    """system.j2 must document relationship_changes extraction rules."""
    out = render("extractor/system.j2")
    assert "relationship_changes" in out
    assert "from_character_name" in out
    assert "to_character_name" in out
    assert "strength" in out
    # Boundary / direction guidance
    assert "单向" in out or "方向" in out


def test_user_prompt_lists_existing_relationships():
    """user.j2 must render existing_relationships (current-valid only)."""
    from types import SimpleNamespace
    chars = [
        SimpleNamespace(id=1, name="李雷", role="protagonist",
                        background="bg", motivation="m", appearance="a",
                        current_state=""),
        SimpleNamespace(id=2, name="韩梅", role="supporting",
                        background="bg2", motivation="m2", appearance="a2",
                        current_state=""),
    ]
    existing_rels = [
        SimpleNamespace(
            from_char_id=1, from_name="李雷",
            to_char_id=2, to_name="韩梅",
            type="旧友", strength=0.5, description="童年同伴",
        ),
    ]
    out = render("extractor/user.j2",
                 project=SimpleNamespace(title="T", genre="g", premise="p"),
                 chapter=SimpleNamespace(title="C", content="x", order_index=3),
                 existing_characters=chars,
                 existing_lore=[],
                 existing_relationships=existing_rels,
                 rejected_suggestions=[],
                 genre_template=None)
    assert "已有关系" in out
    assert "李雷 → 韩梅" in out
    assert "旧友" in out
    assert "0.5" in out


def test_system_prompt_has_events_section():
    """system.j2 must document events extraction rules."""
    out = render("extractor/system.j2")
    assert "events" in out
    assert "involved_character_names" in out
    assert "location_name" in out
    assert "title" in out
    # Guidance about not auto-marking foreshadows
    assert "foreshadows" in out


def test_render_extractor_user_rejected_suggestions():
    """user.j2 renders rejected_suggestions section when present."""
    from types import SimpleNamespace
    chars = [SimpleNamespace(name="李雷", role="protagonist",
                             background="bg", motivation="m", appearance="a",
                             current_state="")]
    rejected = [
        {"entity_description": "人物：韩梅（supporting）", "note": "不准确"},
        {"entity_description": "设定：残月酒馆（location）", "note": ""},
    ]
    out = render("extractor/user.j2",
                 project=SimpleNamespace(title="T", genre="g", premise="p"),
                 chapter=SimpleNamespace(title="C", content="x", order_index=3),
                 existing_characters=chars,
                 existing_lore=[],
                 existing_relationships=[],
                 rejected_suggestions=rejected,
                 genre_template=None)
    assert "已拒绝" in out
    assert "人物：韩梅" in out
    assert "设定：残月酒馆" in out
    assert "不准确" in out  # note rendered


def test_render_extractor_user_empty_rejected():
    """user.j2 omits rejected section when empty list."""
    from types import SimpleNamespace
    chars = [SimpleNamespace(name="李雷", role="protagonist",
                             background="bg", motivation="m", appearance="a",
                             current_state="")]
    out = render("extractor/user.j2",
                 project=SimpleNamespace(title="T", genre="g", premise="p"),
                 chapter=SimpleNamespace(title="C", content="x", order_index=3),
                 existing_characters=chars,
                 existing_lore=[],
                 existing_relationships=[],
                 rejected_suggestions=[],
                 genre_template=None)
    assert "已拒绝" not in out
