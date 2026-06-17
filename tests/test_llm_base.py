from unittest.mock import MagicMock

from app.llm.base import LLMRequest, LLMResponse
from app.llm.providers.claude import ClaudeProvider
from app.llm.router import ModelRouter


def test_llm_request_dataclass():
    req = LLMRequest(model_task="writer_short", system="S", user="U", max_tokens=100)
    assert req.model_task == "writer_short"
    assert req.user == "U"


def test_claude_provider_calls_sdk(monkeypatch):
    fake_resp = MagicMock()
    fake_resp.content = [MagicMock(text="hello world")]
    fake_resp.usage.input_tokens = 10
    fake_resp.usage.output_tokens = 5
    fake_resp.stop_reason = "end_turn"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_resp

    monkeypatch.setattr("app.llm.providers.claude.Anthropic", lambda **kw: fake_client)

    provider = ClaudeProvider(api_key="fake")
    resp = provider.complete(LLMRequest(model_task="writer_short", user="hi", max_tokens=100))
    assert isinstance(resp, LLMResponse)
    assert resp.text == "hello world"
    assert resp.input_tokens == 10
    assert resp.output_tokens == 5

    fake_client.messages.create.assert_called_once()
    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert call_kwargs["max_tokens"] == 100
    assert call_kwargs["messages"] == [{"role": "user", "content": "hi"}]
    assert "system" not in call_kwargs  # empty system → not forwarded


def test_claude_provider_forwards_system_prompt(monkeypatch):
    fake_resp = MagicMock()
    fake_resp.content = [MagicMock(text="ok")]
    fake_resp.usage.input_tokens = 1
    fake_resp.usage.output_tokens = 1
    fake_resp.stop_reason = "end_turn"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_resp

    monkeypatch.setattr("app.llm.providers.claude.Anthropic", lambda **kw: fake_client)

    provider = ClaudeProvider(api_key="fake")
    provider.complete(LLMRequest(model_task="writer_short", user="hi", system="You are a poet"))

    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == "You are a poet"


def test_model_router_resolves_task_to_model():
    router = ModelRouter(default_provider="claude")
    assert router.resolve_model("writer_long") == ("claude", "claude-sonnet-4-6")


def test_model_router_unknown_task_falls_back():
    router = ModelRouter(default_provider="claude")
    provider, model = router.resolve_model("nonexistent_task")
    assert provider == "claude"


def test_claude_provider_accepts_base_url(monkeypatch):
    """ClaudeProvider should pass base_url to Anthropic client when provided."""
    captured_kwargs = {}
    def fake_anthropic(**kwargs):
        captured_kwargs.update(kwargs)
        return MagicMock()
    monkeypatch.setattr("app.llm.providers.claude.Anthropic", fake_anthropic)

    ClaudeProvider(api_key="sk-test", base_url="https://my-proxy.example.com")
    assert captured_kwargs["api_key"] == "sk-test"
    assert captured_kwargs["base_url"] == "https://my-proxy.example.com"


def test_claude_provider_omits_base_url_when_empty(monkeypatch):
    """Empty base_url should not be passed to Anthropic client (use SDK default)."""
    captured_kwargs = {}
    def fake_anthropic(**kwargs):
        captured_kwargs.update(kwargs)
        return MagicMock()
    monkeypatch.setattr("app.llm.providers.claude.Anthropic", fake_anthropic)

    ClaudeProvider(api_key="sk-test", base_url="")
    assert captured_kwargs["api_key"] == "sk-test"
    assert "base_url" not in captured_kwargs

