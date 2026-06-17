from collections.abc import Iterator

from app.config import settings
from app.llm.base import LLMProvider, LLMResponse
from app.llm.providers.claude import ClaudeProvider
from app.llm.providers.openai import OpenAIProvider
from app.llm.streaming import StreamEvent

CLAUDE_ROUTES = {
    "writer_long":  ("claude", "claude-sonnet-4-6"),
    "writer_short": ("claude", "claude-haiku-4-5"),
    "reviewer":     ("claude", "claude-sonnet-4-6"),
    "discuss":      ("claude", "claude-sonnet-4-6"),
    "extractor":    ("claude", "claude-haiku-4-5"),
}


def _build_routes(provider: str) -> dict[str, tuple[str, str]]:
    """Build route table based on selected provider."""
    if provider == "openai":
        # OpenAI-compatible: single model for all tasks (can be split later)
        model = settings.openai_model or "gpt-4o-mini"
        return {task: ("openai", model) for task in CLAUDE_ROUTES}
    # Default: Claude routes
    return dict(CLAUDE_ROUTES)


# Backward-compat alias
DEFAULT_ROUTES = CLAUDE_ROUTES


class ModelRouter:
    def __init__(
        self,
        default_provider: str | None = None,
        routes: dict | None = None,
        api_keys: dict[str, str] | None = None,
    ):
        self.default_provider = default_provider or settings.default_llm_provider
        self.routes = routes or _build_routes(self.default_provider)
        self._api_keys = api_keys or {}
        self._providers: dict[str, LLMProvider] = {}

    def _get_provider(self, name: str) -> LLMProvider:
        if name not in self._providers:
            if name == "claude":
                self._providers[name] = ClaudeProvider(
                    api_key=self._api_keys.get("claude", settings.anthropic_api_key)
                )
            elif name == "openai":
                self._providers[name] = OpenAIProvider(
                    api_key=self._api_keys.get("openai", settings.openai_api_key),
                    base_url=settings.openai_base_url,
                )
            else:
                raise ValueError(f"unknown provider: {name}")
        return self._providers[name]

    def resolve_model(self, task: str) -> tuple[str, str]:
        if task in self.routes:
            return self.routes[task]
        # Unknown task fallback
        return (self.default_provider, self._fallback_model())

    def _fallback_model(self) -> str:
        if self.default_provider == "openai":
            return settings.openai_model or "gpt-4o-mini"
        return "claude-haiku-4-5"

    def complete(self, request) -> LLMResponse:
        provider_name, model = self.resolve_model(request.model_task)
        provider = self._get_provider(provider_name)
        return provider.complete(request, model)

    def stream(self, request) -> Iterator[StreamEvent]:
        provider_name, model = self.resolve_model(request.model_task)
        provider = self._get_provider(provider_name)
        yield from provider.stream(request, model)


# 进程级单例：复用底层 httpx 连接池，避免每请求新建 Anthropic / OpenAI 客户端
default_router = ModelRouter()
