"""M4a: assemble_review_context() tests."""
import pytest
from app.memory.retrieval import assemble_review_context
from app.memory.schema import (
    Chapter, Character, CharacterState, Event, LoreEntry, Project,
    Relationship, WorldOverview,
)


def _db_session(db_session):
    """The conftest db_session fixture already does the right thing."""
    return db_session


def _seed_full_project(db_session):
    p = Project(title="T", genre="g", premise="p")
    db_session.add(p); db_session.flush()

    wo = WorldOverview(project_id=p.id, setting_era="古代", power_system="魔法")
    db_session.add(wo)

    ch1 = Chapter(project_id=p.id, order_index=1, title="C1", content="第一章正文",
                  summary="第一章摘要", status="final")
    ch2 = Chapter(project_id=p.id, order_index=2, title="C2", content="第二章正文",
                  status="draft")
    db_session.add_all([ch1, ch2]); db_session.flush()

    c1 = Character(project_id=p.id, name="李雷", role="protagonist")
    c2 = Character(project_id=p.id, name="韩梅", role="supporting")
    db_session.add_all([c1, c2]); db_session.flush()
    ch2.last_involved_character_ids = [c1.id, c2.id]

    # Character states for c1
    s1 = CharacterState(character_id=c1.id, chapter_id=ch1.id,
                        state_snapshot="警惕", change_summary="初入")
    db_session.add(s1)

    # Relationship: c1→c2 enemies
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="仇人", strength=-0.8, valid_from_chapter=ch1.id,
    ))

    # Event in ch1 with foreshadows
    e1 = Event(project_id=p.id, chapter_id=ch1.id,
               title="伏击", description="李雷被伏击",
               foreshadows=[])
    db_session.add(e1); db_session.flush()
    # Event in ch2 that foreshadows e1 (so e1 has payoff_of=[e2.id])
    e2 = Event(project_id=p.id, chapter_id=ch2.id,
               title="复仇", description="李雷复仇",
               foreshadows=[e1.id])
    db_session.add(e2)

    # Lore entries
    db_session.add(LoreEntry(project_id=p.id, type="location", name="残月酒馆"))
    db_session.add(LoreEntry(project_id=p.id, type="faction", name="守夜人"))

    db_session.commit()
    return p, ch1, ch2, c1, c2


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    from app.memory import session as session_module
    from app.memory.session import _build_engine, init_db
    from sqlalchemy.orm import sessionmaker
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.memory.session.settings.db_path", db_file)
    new_engine = _build_engine(db_file)
    new_session = sessionmaker(bind=new_engine, autoflush=False,
                                autocommit=False, future=True)
    monkeypatch.setattr(session_module, "engine", new_engine)
    monkeypatch.setattr(session_module, "SessionLocal", new_session)
    init_db()
    with new_session() as s:
        yield s


def test_assemble_review_context_minimal(db_session):
    """Single chapter, no states/relationships/events — should not raise."""
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.commit()

    bundle = assemble_review_context(db_session, chapter_id=ch.id)
    assert bundle.chapter.id == ch.id
    assert bundle.characters == []
    assert bundle.character_states_history == {}
    assert bundle.relationships == []
    assert bundle.events == []
    assert bundle.recent_chapter_summaries == []


def test_assemble_review_context_resolves_involved_characters(db_session):
    """Uses chapter.last_involved_character_ids to pick characters."""
    p, ch1, ch2, c1, c2 = _seed_full_project(db_session)
    bundle = assemble_review_context(db_session, chapter_id=ch2.id)
    names = {c.name for c in bundle.characters}
    assert names == {"李雷", "韩梅"}


def test_assemble_review_context_state_history(db_session):
    """Pulls last N states per character."""
    p, ch1, ch2, c1, c2 = _seed_full_project(db_session)
    bundle = assemble_review_context(db_session, chapter_id=ch2.id)
    # c1 has 1 state in ch1
    assert c1.id in bundle.character_states_history
    states = bundle.character_states_history[c1.id]
    assert len(states) == 1
    assert states[0].current_state == "警惕"


def test_assemble_review_context_state_history_limit(db_session):
    """state_history_limit caps number of states."""
    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    chapters = []
    for i in range(1, 6):  # 5 chapters
        ch = Chapter(project_id=p.id, order_index=i, title=f"C{i}", content="x")
        db_session.add(ch); chapters.append(ch)
    db_session.flush()
    c1 = Character(project_id=p.id, name="李雷")
    db_session.add(c1); db_session.flush()
    for ch in chapters:
        db_session.add(CharacterState(
            character_id=c1.id, chapter_id=ch.id,
            state_snapshot=f"state-{ch.order_index}", change_summary="",
        ))
    db_session.commit()

    bundle = assemble_review_context(db_session, chapter_id=chapters[-1].id,
                                      state_history_limit=3)
    assert len(bundle.character_states_history[c1.id]) == 3
    # Newest first
    snapshots = [s.current_state for s in bundle.character_states_history[c1.id]]
    assert snapshots == ["state-5", "state-4", "state-3"]


def test_assemble_review_context_includes_all_relationships(db_session):
    """All project relationships, not just involved-pair."""
    p, ch1, ch2, c1, c2 = _seed_full_project(db_session)
    bundle = assemble_review_context(db_session, chapter_id=ch2.id)
    assert len(bundle.relationships) == 1
    assert bundle.relationships[0].from_name == "李雷"
    assert bundle.relationships[0].to_name == "韩梅"


def test_assemble_review_context_includes_events_with_payoff(db_session):
    """Events have derived payoff_of and is_unpaid."""
    p, ch1, ch2, c1, c2 = _seed_full_project(db_session)
    bundle = assemble_review_context(db_session, chapter_id=ch2.id)
    by_title = {e.title: e for e in bundle.events}
    # e1 (伏击) is foreshadowed by e2 (复仇) → e1.payoff_of=[e2.id]
    assert by_title["伏击"].payoff_of == [by_title["复仇"].id]
    # e2 (复仇) foreshadows e1 (伏击); e1 has no external payoff → e2.is_unpaid
    assert by_title["复仇"].is_unpaid is True


def test_assemble_review_context_excludes_current_chapter_summary(db_session):
    """recent_chapter_summaries does NOT include the chapter being reviewed."""
    p, ch1, ch2, c1, c2 = _seed_full_project(db_session)
    bundle = assemble_review_context(db_session, chapter_id=ch2.id)
    # ch2 has no summary anyway, but ch1 should be present
    assert any(s.title == "C1" for s in bundle.recent_chapter_summaries)
    # Reviewing ch1 → ch1's summary should NOT appear
    bundle_ch1 = assemble_review_context(db_session, chapter_id=ch1.id)
    assert not any(s.title == "C1" for s in bundle_ch1.recent_chapter_summaries)


def test_assemble_review_context_includes_lore(db_session):
    p, ch1, ch2, c1, c2 = _seed_full_project(db_session)
    bundle = assemble_review_context(db_session, chapter_id=ch2.id)
    types = {l.type for l in bundle.lore_entries}
    assert types == {"location", "faction"}


def test_assemble_review_context_includes_active_plot_lines(db_session):
    """assemble_review_context also injects active plot_lines."""
    from app.memory.retrieval import assemble_review_context
    from app.memory.schema import PlotLine

    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    db_session.add(PlotLine(project_id=p.id, type="main", title="主线",
                            status="active", summary="在推进"))
    db_session.commit()

    bundle = assemble_review_context(db_session, chapter_id=ch.id)
    titles = {pl.title for pl in bundle.plot_lines}
    assert "主线" in titles
