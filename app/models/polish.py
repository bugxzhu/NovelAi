from pydantic import BaseModel


class PolishRequest(BaseModel):
    selected_text: str | None = None  # null = polish whole chapter


class PolishResponse(BaseModel):
    polished_text: str
    is_selection: bool  # true if polished a selection, false if whole chapter
    log_id: int
