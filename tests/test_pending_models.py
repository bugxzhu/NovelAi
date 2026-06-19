from datetime import UTC, datetime

from app.models.pending import (
    PendingUpdateRead,
    PendingUpdateDetail,
    FinalizeResponse,
)


def test_pending_read_minimal():
    now = datetime.now(UTC)
    p = PendingUpdateRead(
        id=1, project_id=1, chapter_id=1,
        update_type="hard_fact", operation="create",
        target_table="characters", target_id=None,
        reason="", status="pending",
        entity_name="韩梅", entity_type="", field_name="",
        old_value="", proposed_value="酒馆老板娘",
        created_at=now, updated_at=now,
    )
    assert p.entity_name == "韩梅"
    # Read does not expose proposed_change
    assert not hasattr(p, "proposed_change")


def test_pending_detail_has_proposed_change():
    now = datetime.now(UTC)
    p = PendingUpdateDetail(
        id=1, project_id=1, chapter_id=1,
        update_type="hard_fact", operation="create",
        target_table="characters", target_id=None,
        reason="", status="pending",
        entity_name="韩梅", entity_type="", field_name="",
        old_value="", proposed_value="酒馆老板娘",
        proposed_change={"name": "韩梅", "role": "supporting", "description": "酒馆老板娘"},
        decision_note="", decided_at=None,
        extractor_model="claude-haiku-4-5", extractor_log_id=42,
        chapter_title="第二章", target_entity_name=None,
        created_at=now, updated_at=now,
    )
    assert p.proposed_change["name"] == "韩梅"
    assert p.chapter_title == "第二章"


def test_finalize_response():
    r = FinalizeResponse(
        chapter_id=1, summary="...",
        pending_created=3, log_id=42,
    )
    assert r.pending_created == 3


def test_accept_response_includes_no_extra_fields():
    # accept endpoint returns PendingUpdateRead, not Detail
    from app.models.pending import AcceptRejectResponse
    now = datetime.now(UTC)
    r = AcceptRejectResponse(
        id=1, project_id=1, chapter_id=1,
        update_type="hard_fact", operation="create",
        target_table="characters", target_id=None,
        reason="", status="accepted",
        entity_name="韩梅", entity_type="", field_name="",
        old_value="", proposed_value="酒馆老板娘",
        created_at=now, updated_at=now,
    )
    assert r.status == "accepted"
