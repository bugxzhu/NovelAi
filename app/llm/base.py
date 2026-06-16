from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class LLMRequest:
    model_task: str             # writer_long / writer_short / reviewer / discuss / extractor / embedding
    user: str
    system: str = ""
    max_tokens: int = 2048
    temperature: float = 0.7
    metadata: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""
    raw: object = None


class LLMProvider(Protocol):
    name: str

    def complete(self, request: LLMRequest, model: str) -> LLMResponse: ...
