class ChapterNotFoundError(Exception):
    def __init__(self, chapter_id: int):
        self.chapter_id = chapter_id
        super().__init__(f"chapter not found: {chapter_id}")


class InvalidContextError(Exception):
    """One or more context entity IDs are invalid (nonexistent or wrong project)."""
    def __init__(
        self,
        *,
        invalid_character_ids: list[int] | None = None,
        invalid_location_id: int | None = None,
    ):
        self.invalid_character_ids = list(invalid_character_ids or [])
        self.invalid_location_id = invalid_location_id
        parts = []
        if self.invalid_character_ids:
            parts.append(f"invalid character_ids={self.invalid_character_ids}")
        if self.invalid_location_id is not None:
            parts.append(f"invalid location_id={self.invalid_location_id}")
        super().__init__("; ".join(parts) or "invalid context")


class ExtractionError(Exception):
    """LLM extraction failed (invalid JSON, missing fields, etc.)."""


class ReviewError(Exception):
    """LLM review failed (invalid JSON, missing issues_by_category, max_tokens, etc.)."""


class DiscussError(Exception):
    """LLM discuss failed (invalid JSON, max_tokens, etc.)."""
