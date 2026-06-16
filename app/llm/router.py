from app.llm.base import LLMProvider, LLMResponse
from app.llm.providers.claude import ClaudeProvider

DEFAULT_ROUTES = {
    "writer_long":  ("claude", "claude-sonnet-4-6"),
    "writer_short": ("claude", "claude-haiku-4-5"),
    "reviewer":     ("claude", "claude-sonnet-4-6"),
    "discuss":      ("claude", "claude-sonnet-4-6"),
    "extractor":    ("claude", "claude-haiku-4-5"),
}


class ModelRouter:
    def __init__(self, default_provider: str = "claude", routes: dict | None = None):
        self.default_provider = default_provider
        self.routes = routes or DEFAULT_ROUTES
        self._providers: dict[str, LLMProvider] = {}

    def _get_provider(self, name: str) -> LLMProvider:
        if name not in self._providers:
            if name == "claude":
                self._providers[name] = ClaudeProvider()
            else:
                raise ValueError(f"unknown provider: {name}")
        return self._providers[name]

    def resolve_model(self, task: str) -> tuple[str, str]:
        if task in self.routes:
            return self.routes[task]
        # 未知任务 fallback：用默认 provider + 一个保守的模型
        return (self.default_provider, "claude-haiku-4-5")

    def complete(self, request) -> LLMResponse:
        provider_name, model = self.resolve_model(request.model_task)
        provider = self._get_provider(provider_name)
        return provider.complete(request, model)
