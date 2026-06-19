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
    )
    assert "夜行记" in out
    # Empty loops should not raise
    assert "已有人物（0" in out
    assert "已有设定（0" in out


def test_render_user_missing_var_raises():
    with pytest.raises(UndefinedError):
        render("extractor/user.j2", project=_fake_project())
