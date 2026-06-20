from collections.abc import Iterator

from anthropic import Anthropic

from app.llm.base import LLMRequest, LLMResponse
from app.llm.streaming import StreamEvent


class ClaudeProvider:
    name = "claude"

    def __init__(self, api_key: str = "", base_url: str = ""):
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = Anthropic(**kwargs)

    def complete(self, request: LLMRequest, model: str | None = None) -> LLMResponse:
        kwargs = {
            "model": model or "claude-sonnet-4-6",
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

    def stream(self, request: LLMRequest, model: str | None = None) -> Iterator[StreamEvent]:
        kwargs = {
            "model": model or "claude-sonnet-4-6",
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.user}],
        }
        if request.system:
            kwargs["system"] = request.system
        try:
            with self._client.messages.stream(**kwargs) as stream:
                for chunk in stream.text_stream:
                    yield StreamEvent(type="token", text=chunk)
                final = stream.get_final_message()
                yield StreamEvent(
                    type="done",
                    input_tokens=getattr(final.usage, "input_tokens", 0),
                    output_tokens=getattr(final.usage, "output_tokens", 0),
                    stop_reason=getattr(final, "stop_reason", ""),
                    raw=final,
                )
        except Exception as e:
            yield StreamEvent(
                type="error",
                error_message=str(e),
                error_code=type(e).__name__,
            )

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """Anthropic does not provide an embeddings API."""
        raise NotImplementedError(
            "Anthropic does not provide embeddings API. "
            "Set NOVELAI_LLM_PROVIDER=openai or configure a separate embedding endpoint."
        )
