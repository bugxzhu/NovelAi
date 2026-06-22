from pydantic import BaseModel


class PolishRequest(BaseModel):
    selected_text: str | None = None  # null = polish whole chapter
    direction: str = ""


class PolishResponse(BaseModel):
    polished_texts: list[str]   # 1 for whole chapter, 2 for selection
    is_selection: bool          # true if polished a selection, false if whole chapter
    direction: str
    log_id: int
