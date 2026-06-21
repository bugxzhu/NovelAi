import pytest

from app.memory.errors import ChapterNotFoundError, InvalidContextError
from app.memory.retrieval import (
    ChapterSummary,
    CharacterStateSnapshot,
    ContextBundle,
    assemble_context,
)


def _seed_project_with_chars(db_session, n_chars=2):
    from app.memory.schema import Character, Project, WorldOverview
    p = Project(title="TestNovel", genre="fantasy", premise="A test.",
                main_theme="courage", tone="epic")
    db_session.add(p); db_session.flush()
    wo = WorldOverview(project_id=p.id, setting_era="Medieval",
                       power_system="Magic")
    db_session.add(wo)
    chars = []
    for i in range(n_chars):
        c = Character(project_id=p.id, name=f"Char{i}",
                      role="protagonist", current_state=f"state{i}")
        db_session.add(c); chars.append(c)
    db_session.flush()
    return p, chars


def _seed_chapter(db_session, project_id, order_index, title, summary=""):
    from app.memory.schema import Chapter
    ch = Chapter(project_id=project_id, order_index=order_index,
                 title=title, summary=summary)
    db_session.add(ch); db_session.flush()
    return ch


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


def test_assemble_basic(db_session):
    p, chars = _seed_project_with_chars(db_session, n_chars=2)
    ch = _seed_chapter(db_session, p.id, 1, "Chapter 1")
    db_session.commit()
    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[chars[0].id, chars[1].id],
    )
    assert isinstance(bundle, ContextBundle)
    assert bundle.project.id == p.id
    assert bundle.world_overview is not None
    assert bundle.world_overview.setting_era == "Medieval"
    assert len(bundle.characters) == 2
    assert {c.name for c in bundle.characters} == {"Char0", "Char1"}
    assert chars[0].id in bundle.character_states
    assert bundle.character_states[chars[0].id].current_state == "state0"


def test_assemble_chapter_not_found(db_session):
    with pytest.raises(ChapterNotFoundError):
        assemble_context(
            db_session, chapter_id=99999, beat_text="x",
            involved_character_ids=[1],
        )


def test_assemble_with_no_world_overview(db_session):
    from app.memory.schema import Character, Chapter, Project
    p = Project(title="NoWO")
    db_session.add(p); db_session.flush()
    c = Character(project_id=p.id, name="C")
    db_session.add(c)
    ch = Chapter(project_id=p.id, order_index=1, title="C1")
    db_session.add(ch); db_session.commit()
    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[c.id],
    )
    assert bundle.world_overview is None


def test_assemble_m3_fields_are_empty(db_session):
    p, chars = _seed_project_with_chars(db_session, 1)
    ch = _seed_chapter(db_session, p.id, 1, "C1")
    db_session.commit()
    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[chars[0].id],
    )
    assert bundle.relationships == []
    assert bundle.plot_lines == []
    assert len(bundle.character_states) == 1


def test_assemble_recent_summaries_excludes_current(db_session):
    p, chars = _seed_project_with_chars(db_session, 1)
    ch1 = _seed_chapter(db_session, p.id, 1, "C1", summary="prev1")
    ch2 = _seed_chapter(db_session, p.id, 2, "C2", summary="prev2")
    db_session.commit()
    bundle = assemble_context(
        db_session, chapter_id=ch2.id, beat_text="x",
        involved_character_ids=[chars[0].id],
    )
    ids = [s.chapter_id for s in bundle.recent_chapter_summaries]
    assert ch2.id not in ids
    assert ch1.id in ids


def test_assemble_recent_summaries_skips_empty(db_session):
    p, chars = _seed_project_with_chars(db_session, 1)
    ch1 = _seed_chapter(db_session, p.id, 1, "C1", summary="")  # empty
    ch2 = _seed_chapter(db_session, p.id, 2, "C2", summary="real")
    db_session.commit()
    bundle = assemble_context(
        db_session, chapter_id=ch2.id, beat_text="x",
        involved_character_ids=[chars[0].id],
    )
    ids = [s.chapter_id for s in bundle.recent_chapter_summaries]
    assert ch1.id not in ids


def test_assemble_rejects_cross_project_character(db_session):
    from app.memory.schema import Character, Chapter, Project
    p1 = Project(title="A"); db_session.add(p1); db_session.flush()
    p2 = Project(title="B"); db_session.add(p2); db_session.flush()
    c2 = Character(project_id=p2.id, name="c2")
    db_session.add(c2)
    ch1 = Chapter(project_id=p1.id, order_index=1, title="c1")
    db_session.add(ch1); db_session.commit()
    with pytest.raises(InvalidContextError) as exc:
        assemble_context(
            db_session, chapter_id=ch1.id, beat_text="x",
            involved_character_ids=[c2.id],
        )
    assert c2.id in exc.value.invalid_character_ids


def test_assemble_rejects_nonexistent_character(db_session):
    p, chars = _seed_project_with_chars(db_session, 1)
    ch = _seed_chapter(db_session, p.id, 1, "C1")
    db_session.commit()
    with pytest.raises(InvalidContextError) as exc:
        assemble_context(
            db_session, chapter_id=ch.id, beat_text="x",
            involved_character_ids=[chars[0].id, 99999],
        )
    assert 99999 in exc.value.invalid_character_ids
    assert chars[0].id not in exc.value.invalid_character_ids


def test_assemble_rejects_cross_project_location(db_session):
    from app.memory.schema import Chapter, LoreEntry, Project
    p1 = Project(title="A"); db_session.add(p1); db_session.flush()
    p2 = Project(title="B"); db_session.add(p2); db_session.flush()
    loc2 = LoreEntry(project_id=p2.id, type="location", name="loc2")
    db_session.add(loc2)
    ch1 = Chapter(project_id=p1.id, order_index=1, title="c1")
    db_session.add(ch1); db_session.commit()
    with pytest.raises(InvalidContextError) as exc:
        assemble_context(
            db_session, chapter_id=ch1.id, beat_text="x",
            involved_character_ids=[],
            location_id=loc2.id,
        )
    assert exc.value.invalid_location_id == loc2.id


def test_assemble_location_with_ancestors(db_session):
    from app.memory.schema import Chapter, LoreEntry, Project
    p = Project(title="A"); db_session.add(p); db_session.flush()
    kingdom = LoreEntry(project_id=p.id, type="location", name="Kingdom")
    db_session.add(kingdom); db_session.flush()
    city = LoreEntry(project_id=p.id, type="location", name="City",
                     parent_id=kingdom.id)
    db_session.add(city); db_session.flush()
    district = LoreEntry(project_id=p.id, type="location", name="District",
                         parent_id=city.id)
    db_session.add(district)
    ch = Chapter(project_id=p.id, order_index=1, title="C1")
    db_session.add(ch); db_session.commit()
    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[],
        location_id=district.id,
    )
    names = [l.name for l in bundle.location_lore]
    assert names == ["Kingdom", "City", "District"]


def test_assemble_includes_faction_from_character_affiliations(db_session):
    from app.memory.schema import Chapter, Character, LoreEntry, Project
    p = Project(title="A"); db_session.add(p); db_session.flush()
    faction = LoreEntry(project_id=p.id, type="faction", name="守夜人")
    db_session.add(faction); db_session.flush()
    c = Character(project_id=p.id, name="C", affiliations=[faction.id])
    db_session.add(c)
    ch = Chapter(project_id=p.id, order_index=1, title="C1")
    db_session.add(ch); db_session.commit()
    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[c.id],
    )
    assert any(f.name == "守夜人" for f in bundle.faction_lore)


def test_assemble_populates_relationships_for_involved_pair(db_session):
    """When 2+ characters are involved, their current-valid relationships appear in bundle."""
    from app.memory.schema import Chapter, Character, Project, Relationship

    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    c1 = Character(project_id=p.id, name="李雷")
    c2 = Character(project_id=p.id, name="韩梅")
    db_session.add_all([c1, c2]); db_session.flush()
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="旧友", strength=0.5, valid_from_chapter=0,
    ))
    db_session.commit()

    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[c1.id, c2.id],
    )
    assert len(bundle.relationships) == 1
    r = bundle.relationships[0]
    assert r.from_char_id == c1.id
    assert r.to_char_id == c2.id
    assert r.from_name == "李雷"
    assert r.to_name == "韩梅"
    assert r.type == "旧友"
    assert r.strength == 0.5


def test_assemble_excludes_relationships_with_uninvolved(db_session):
    """A-B relationship, but bundle only involves A and C → not included."""
    from app.memory.schema import Chapter, Character, Project, Relationship

    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    c1 = Character(project_id=p.id, name="李雷")
    c2 = Character(project_id=p.id, name="韩梅")  # not involved
    c3 = Character(project_id=p.id, name="王五")
    db_session.add_all([c1, c2, c3]); db_session.flush()
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="旧友", strength=0.5, valid_from_chapter=0,
    ))
    db_session.commit()

    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[c1.id, c3.id],
    )
    assert bundle.relationships == []


def test_assemble_excludes_history_relationships(db_session):
    """Soft-closed (history) relationships are NOT injected."""
    from app.memory.schema import Chapter, Character, Project, Relationship

    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    c1 = Character(project_id=p.id, name="李雷")
    c2 = Character(project_id=p.id, name="韩梅")
    db_session.add_all([c1, c2]); db_session.flush()
    # Only a soft-closed history row
    db_session.add(Relationship(
        project_id=p.id, from_char_id=c1.id, to_char_id=c2.id,
        type="旧友", strength=0.5,
        valid_from_chapter=0, valid_to_chapter=ch.id,
    ))
    db_session.commit()

    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[c1.id, c2.id],
    )
    assert bundle.relationships == []


def test_assemble_context_includes_active_plot_lines(db_session):
    """assemble_context injects active plot_lines into ContextBundle."""
    from app.memory.retrieval import assemble_context
    from app.memory.schema import Chapter, PlotLine, Project

    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    db_session.add(PlotLine(project_id=p.id, type="main", title="主线A",
                            status="active", summary="进展"))
    db_session.add(PlotLine(project_id=p.id, type="sub", title="支线B",
                            status="planned", summary=""))
    db_session.commit()

    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[],
    )
    titles = {pl.title for pl in bundle.plot_lines}
    assert "主线A" in titles
    assert "支线B" not in titles  # planned, not active


def test_assemble_context_excludes_non_active(db_session):
    """resolved/abandoned/planned plot_lines not injected."""
    from app.memory.retrieval import assemble_context
    from app.memory.schema import Chapter, PlotLine, Project

    p = Project(title="T", genre="", premise="")
    db_session.add(p); db_session.flush()
    ch = Chapter(project_id=p.id, order_index=1, title="C1", content="x")
    db_session.add(ch); db_session.flush()
    for s in ("planned", "resolved", "abandoned"):
        db_session.add(PlotLine(project_id=p.id, title=f"PL-{s}", status=s))
    db_session.commit()

    bundle = assemble_context(
        db_session, chapter_id=ch.id, beat_text="x",
        involved_character_ids=[],
    )
    assert bundle.plot_lines == []
