"""M4a: reviewer prompt rendering tests."""
from types import SimpleNamespace

from app.llm.prompts import render


def _stub_project():
    return SimpleNamespace(title="T", genre="g", main_theme="mt", tone="t", premise="p")


def _stub_chapter():
    return SimpleNamespace(order_index=3, title="C3", content="正文...")


def test_render_reviewer_system():
    """system.j2 contains 5-dimension rules + JSON schema + location constraint."""
    out = render("reviewer/system.j2")
    assert "人物一致性" in out and "character" in out
    assert "关系合理性" in out and "relationship" in out
    assert "情节矛盾" in out and "plot" in out
    assert "伏笔完整性" in out and "foreshadow" in out
    assert "世界观一致性" in out and "worldview" in out
    assert "issues_by_category" in out
    # location constraint
    assert "逐字摘录" in out or "verbatim" in out.lower()


def test_render_reviewer_user_minimal():
    """user.j2 renders with empty context fields (no world_overview, no chars)."""
    out = render(
        "reviewer/user.j2",
        project=_stub_project(),
        world_overview=None,
        chapter=_stub_chapter(),
        characters=[],
        character_states_history={},
        relationships=[],
        events=[],
        lore_entries=[],
        plot_lines=[],
        recent_chapter_summaries=[],
        milestones=[],
        genre_template=None,
    )
    assert "C3" in out
    assert "正文..." in out


def test_render_reviewer_user_full():
    """user.j2 renders all context fields."""
    char = SimpleNamespace(
        id=1, name="李雷", role="protagonist",
        personality={"brave": True}, speech_style="直接",
        motivation="复仇", background="孤儿",
    )
    state = SimpleNamespace(current_state="警惕", change_summary="初入")
    rel = SimpleNamespace(
        from_name="李雷", to_name="韩梅",
        type="仇人", strength=-0.8, description="伏击",
    )
    event = SimpleNamespace(
        chapter_order=1, title="伏击", description="李雷被伏击",
        foreshadows=[], payoff_of=[], payoff_of_titles=[],
        is_unpaid=False,
    )
    lore = SimpleNamespace(type="location", name="残月酒馆", description="酒馆")
    summary = SimpleNamespace(order_index=1, title="C1", summary="摘要")

    wo = SimpleNamespace(
        setting_era="古代", power_system="魔法",
        rules_and_taboos="禁忌", geography_summary="地理",
        culture_summary="文化",
    )

    out = render(
        "reviewer/user.j2",
        project=_stub_project(),
        world_overview=wo,
        chapter=_stub_chapter(),
        characters=[char],
        character_states_history={1: [state]},
        relationships=[rel],
        events=[event],
        lore_entries=[lore],
        plot_lines=[],
        recent_chapter_summaries=[summary],
        milestones=[],
        genre_template=None,
    )
    assert "李雷" in out
    assert "仇人" in out
    assert "伏击" in out
    assert "残月酒馆" in out
    assert "摘要" in out
    assert "魔法" in out  # world_overview.power_system


def test_render_reviewer_user_has_plot_lines():
    """reviewer/user.j2 renders plot_lines section."""
    from types import SimpleNamespace
    pl = SimpleNamespace(type="main", title="复仇之路", summary="在推进")
    out = render(
        "reviewer/user.j2",
        project=SimpleNamespace(title="T", genre="g", main_theme="m",
                                tone="t", premise="p"),
        world_overview=None,
        chapter=SimpleNamespace(order_index=1, title="C1", content="正文"),
        characters=[],
        character_states_history={},
        relationships=[],
        events=[],
        lore_entries=[],
        plot_lines=[pl],
        recent_chapter_summaries=[],
        milestones=[],
        genre_template=None,
    )
    assert "当前情节线" in out
    assert "复仇之路" in out


def test_render_reviewer_user_has_milestones():
    """reviewer/user.j2 renders milestones section."""
    from types import SimpleNamespace
    m = SimpleNamespace(status="planned", title="真相揭示", type="转折",
                        chapter_start=5, chapter_end=7, description="关键转折")
    out = render(
        "reviewer/user.j2",
        project=SimpleNamespace(title="T", genre="g", main_theme="m",
                                tone="t", premise="p"),
        world_overview=None,
        chapter=SimpleNamespace(order_index=1, title="C1", content="正文"),
        characters=[], character_states_history={},
        relationships=[], events=[], lore_entries=[],
        plot_lines=[],
        milestones=[m],
        recent_chapter_summaries=[],
        genre_template=None,
    )
    assert "故事蓝图" in out
    assert "真相揭示" in out
