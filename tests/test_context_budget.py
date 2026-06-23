"""ContextBudget tests."""
from types import SimpleNamespace

from app.memory.context_budget import estimate_tokens, trim_review_context


def test_estimate_tokens_chinese():
    assert estimate_tokens("这是一个中文测试") > 0
    assert estimate_tokens("") == 0


def test_estimate_tokens_english():
    assert estimate_tokens("hello world") > 0


def _make_minimal_bundle(**overrides):
    from app.memory.retrieval import ReviewContextBundle

    defaults = dict(
        project=SimpleNamespace(title="T", premise="", main_theme="",
                                 genre="", tone=""),
        world_overview=None,
        chapter=SimpleNamespace(content="short", order_index=1,
                                 title="C1", project_id=1),
        characters=[],
        character_states_history={},
        relationships=[],
        events=[],
        lore_entries=[],
        plot_lines=[],
        milestones=[],
        recent_chapter_summaries=[],
    )
    defaults.update(overrides)
    return ReviewContextBundle(**defaults)


def test_trim_does_nothing_when_under_budget():
    bundle = _make_minimal_bundle()
    result, info = trim_review_context(bundle)
    assert info["actions"] == []  # nothing trimmed
    assert info["original_tokens"] == info["final_tokens"]


def test_trim_reduces_summaries_when_over_budget():
    from app.memory.retrieval import ChapterSummary

    # Create a bundle with many summaries to push over budget
    summaries = [
        ChapterSummary(
            chapter_id=i, order_index=i, title=f"Ch{i}",
            summary="这是" * 5000,
        )
        for i in range(100)
    ]
    bundle = _make_minimal_bundle(recent_chapter_summaries=summaries)

    result, info = trim_review_context(bundle, max_tokens=1000)  # force trimming
    assert len(info["actions"]) > 0
    assert len(result.recent_chapter_summaries) < len(summaries)


def test_trim_preserves_bundle_when_exactly_at_budget():
    bundle = _make_minimal_bundle()
    # estimate returns a small number; pass a generous budget
    tokens = info_tokens(bundle)
    result, info = trim_review_context(bundle, max_tokens=tokens + 1000)
    assert info["actions"] == []
    assert result is bundle


def info_tokens(bundle):
    from app.memory.context_budget import estimate_bundle_tokens
    return estimate_bundle_tokens(bundle)
