from anthropic import Anthropic

from app.llm.base import LLMRequest, LLMResponse


class ClaudeProvider:
    name = "claude"

    def __init__(self, api_key: str = ""):
        self._client = Anthropic(api_key=api_key)

    def complete(self, request: LLMRequest, model: str | None = None) -> LLMResponse:
        kwargs = {
            "model": model or "claude-haiku-4-5",
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.user}],
        }
        if request.system:
            kwargs["system"] = request.system
        resp = self._client.messages.create(**kwargs)
        text = "".join(block.text for block in resp.content if hasattr(block, "text"))
        return LLMResponse(
            text=text,
            input_tokens=getattr(resp.usage, "input_tokens", 0),
            output_tokens=getattr(resp.usage, "output_tokens", 0),
            stop_reason=getattr(resp, "stop_reason", ""),
            raw=resp,
        )
