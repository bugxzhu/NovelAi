from dataclasses import dataclass
from typing import Literal


@dataclass
class StreamEvent:
    """Unified event type for LLM streaming output."""
    type: Literal["token", "done", "error"]
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""
    error_message: str = ""
    error_code: str = ""
    raw: object = None
