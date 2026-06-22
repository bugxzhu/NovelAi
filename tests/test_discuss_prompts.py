"""M4b-2: discuss prompt tests."""
from types import SimpleNamespace
from app.llm.prompts import render


def test_render_discuss_system():
    out = render("discuss/system.j2")
    assert "3" in out and "分支" in out
    assert "branches" in out
    assert "recommended" in out
    assert "conflicts" in out
    assert "opportunities" in out
    assert "character_impact" in out


def test_render_discuss_user_minimal():
    out = render(
        "discuss/user.j2",
        project=SimpleNamespace(title="T", genre="g", main_theme="m",
                                tone="t", premise="p"),
        world_overview=None,
        chapter=SimpleNamespace(order_index=1, title="C1", content="正文"),
        characters=[], character_states_history={},
        relationships=[], events=[], lore_entries=[],
        plot_lines=[], milestones=[],
        recent_chapter_summaries=[],
        question="如果让李雷和韩梅和解？",
        selected_text="",
    )
    assert "如果让李雷和韩梅和解？" in out
    assert "正文" in out


def test_render_discuss_user_full():
    char = SimpleNamespace(
        id=1, name="李雷", role="protagonist",
        personality={"brave": True}, speech_style="直接",
        motivation="复仇", background="孤儿",
    )
    state = SimpleNamespace(current_state="警惕", change_summary="初入")
    pl = SimpleNamespace(type="main", title="复仇", status="active", summary="在推进")
    m = SimpleNamespace(status="planned", title="高潮", type="转折",
                        chapter_start=8, chapter_end=10, description="关键")

    out = render(
        "discuss/user.j2",
        project=SimpleNamespace(title="T", genre="g", main_theme="m",
                                tone="t", premise="p"),
        world_overview=SimpleNamespace(
            setting_era="古代", power_system="魔法",
            rules_and_taboos="禁忌", geography_summary="地理",
            culture_summary="文化"),
        chapter=SimpleNamespace(order_index=1, title="C1", content="正文"),
        characters=[char],
        character_states_history={1: [state]},
        relationships=[],
        events=[],
        lore_entries=[],
        plot_lines=[pl],
        milestones=[m],
        recent_chapter_summaries=[],
        question="如果？",
        selected_text="",
    )
    assert "李雷" in out
    assert "复仇" in out
    assert "高潮" in out
    assert "如果？" in out
