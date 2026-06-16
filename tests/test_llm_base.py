from unittest.mock import MagicMock

from app.llm.base import LLMRequest, LLMResponse
from app.llm.providers.claude import ClaudeProvider
from app.llm.router import ModelRouter


def test_llm_request_dataclass():
    req = LLMRequest(model_task="writer_short", system="S", user="U", max_tokens=100)
    assert req.model_task == "writer_short"
    assert req.user == "U"


def test_claude_provider_calls_sdk(monkeypatch):
    fake_msg = MagicMock()
    fake_msg.content = [MagicMock(text="hello world")]
    fake_resp = MagicMock()
    fake_resp.content = [MagicMock(text="hello world")]
    fake_resp.usage.input_tokens = 10
    fake_resp.usage.output_tokens = 5
    fake_resp.stop_reason = "end_turn"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_resp

    monkeypatch.setattr("app.llm.providers.claude.Anthropic", lambda **kw: fake_client)

    provider = ClaudeProvider(api_key="fake")
    resp = provider.complete(LLMRequest(model_task="writer_short", user="hi"))
    assert isinstance(resp, LLMResponse)
    assert resp.text == "hello world"
    assert resp.input_tokens == 10
    assert resp.output_tokens == 5


def test_model_router_resolves_task_to_model():
    router = ModelRouter(default_provider="claude")
    assert router.resolve_model("writer_long") == ("claude", "claude-sonnet-4-6")


def test_model_router_unknown_task_falls_back():
    router = ModelRouter(default_provider="claude")
    provider, model = router.resolve_model("nonexistent_task")
    assert provider == "claude"
