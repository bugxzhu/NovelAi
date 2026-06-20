from collections.abc import Iterator

from openai import OpenAI

from app.llm.base import LLMRequest, LLMResponse
from app.llm.streaming import StreamEvent


class OpenAIProvider:
    """OpenAI-compatible provider. Works with OpenAI / Azure OpenAI / DashScope /
    Ollama / vLLM / LM Studio / any endpoint exposing the OpenAI chat API."""

    name = "openai"

    def __init__(self, api_key: str = "", base_url: str = ""):
        # Empty base_url -> OpenAI SDK uses its default (https://api.openai.com/v1)
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)

    def _build_messages(self, request: LLMRequest) -> list[dict]:
        msgs = []
        if request.system:
            msgs.append({"role": "system", "content": request.system})
        msgs.append({"role": "user", "content": request.user})
        return msgs

    def complete(self, request: LLMRequest, model: str | None = None) -> LLMResponse:
        resp = self._client.chat.completions.create(
            model=model or "gpt-4o-mini",
            messages=self._build_messages(request),
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        choice = resp.choices[0]
        text = choice.message.content or ""
        usage = resp.usage
        return LLMResponse(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
            stop_reason=getattr(choice.finish_reason, "", "") if hasattr(choice, "finish_reason") else "",
            raw=resp,
        )

    def stream(self, request: LLMRequest, model: str | None = None) -> Iterator[StreamEvent]:
        try:
            stream = self._client.chat.completions.create(
                model=model or "gpt-4o-mini",
                messages=self._build_messages(request),
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                stream=True,
                stream_options={"include_usage": True},
            )
            input_tokens = 0
            output_tokens = 0
            finish_reason = ""
            for chunk in stream:
                # Text delta
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    text = getattr(delta, "content", None)
                    if text:
                        yield StreamEvent(type="token", text=text)
                    fr = getattr(chunk.choices[0], "finish_reason", None)
                    if fr:
                        finish_reason = fr
                # Usage (typically only in the final chunk when stream_options.include_usage=True)
                if chunk.usage:
                    input_tokens = getattr(chunk.usage, "prompt_tokens", 0)
                    output_tokens = getattr(chunk.usage, "completion_tokens", 0)
            yield StreamEvent(
                type="done",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                stop_reason=finish_reason,
            )
        except Exception as e:
            yield StreamEvent(
                type="error",
                error_message=str(e),
                error_code=type(e).__name__,
            )

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """OpenAI-compatible embeddings endpoint.

        Works with: OpenAI text-embedding-3-small/large, DashScope text-embedding-v2,
        Ollama bge-m3, vLLM, LM Studio, etc.
        """
        resp = self._client.embeddings.create(model=model, input=texts)
        return [d.embedding for d in resp.data]
