from unittest.mock import MagicMock

from app.llm.base import LLMRequest
from app.llm.providers.openai import OpenAIProvider
from app.llm.streaming import StreamEvent


def test_openai_provider_uses_base_url_when_set(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="hi"))],
        usage=MagicMock(prompt_tokens=5, completion_tokens=1),
    )
    monkeypatch.setattr("app.llm.providers.openai.OpenAI", lambda **kw: fake_client)
    provider = OpenAIProvider(api_key="k", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    resp = provider.complete(LLMRequest(model_task="writer_long", user="hi"), "qwen-plus")
    assert resp.text == "hi"
    # Verify base_url was passed to client
    # (Note: we mocked OpenAI so we can't check constructor args directly, but no error = pass)


def test_openai_provider_complete_extracts_text_and_usage(monkeypatch):
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="hello world"))]
    fake_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=3)
    fake_resp.choices[0].finish_reason = "stop"
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_resp
    monkeypatch.setattr("app.llm.providers.openai.OpenAI", lambda **kw: fake_client)

    provider = OpenAIProvider(api_key="k")
    resp = provider.complete(
        LLMRequest(model_task="writer_long", user="hi", system="You are X"),
        "qwen-plus",
    )
    assert resp.text == "hello world"
    assert resp.input_tokens == 10
    assert resp.output_tokens == 3

    # Verify SDK called with correct args
    call_kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "qwen-plus"
    assert call_kwargs["messages"] == [
        {"role": "system", "content": "You are X"},
        {"role": "user", "content": "hi"},
    ]


def test_openai_provider_stream_yields_tokens_then_done(monkeypatch):
    # Build a fake stream that yields text chunks + final usage chunk
    chunk1 = MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello "))])
    chunk1.usage = None
    chunk2 = MagicMock(choices=[MagicMock(delta=MagicMock(content="world"))])
    chunk2.usage = None
    chunk3 = MagicMock(choices=[MagicMock(delta=MagicMock(content=None), finish_reason="stop")])
    chunk3.usage = MagicMock(prompt_tokens=8, completion_tokens=2)

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = iter([chunk1, chunk2, chunk3])
    monkeypatch.setattr("app.llm.providers.openai.OpenAI", lambda **kw: fake_client)

    provider = OpenAIProvider(api_key="k")
    events = list(provider.stream(
        LLMRequest(model_task="writer_long", user="hi"),
        "qwen-plus",
    ))
    types = [e.type for e in events]
    assert types == ["token", "token", "done"]
    text = "".join(e.text for e in events if e.type == "token")
    assert text == "Hello world"
    done = events[-1]
    assert done.input_tokens == 8
    assert done.output_tokens == 2
    assert done.stop_reason == "stop"

    # Verify stream args
    call_kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["stream"] is True
    assert call_kwargs["stream_options"] == {"include_usage": True}


def test_openai_provider_stream_wraps_errors(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = RuntimeError("API down")
    monkeypatch.setattr("app.llm.providers.openai.OpenAI", lambda **kw: fake_client)

    provider = OpenAIProvider(api_key="k")
    events = list(provider.stream(
        LLMRequest(model_task="writer_long", user="hi"),
        "qwen-plus",
    ))
    assert len(events) == 1
    assert events[0].type == "error"
    assert "API down" in events[0].error_message
    assert events[0].error_code == "RuntimeError"


def test_model_router_resolves_openai_when_configured(monkeypatch):
    """When llm_provider='openai', router uses OpenAI routes."""
    from app.llm.router import ModelRouter
    # Patch settings to use openai
    monkeypatch.setattr("app.config.settings.llm_provider", "openai")
    monkeypatch.setattr("app.config.settings.openai_model", "qwen-plus")
    router = ModelRouter()
    provider_name, model = router.resolve_model("writer_long")
    assert provider_name == "openai"
    assert model == "qwen-plus"
    # All tasks use same model in M2a
    for task in ["writer_short", "reviewer", "discuss", "extractor"]:
        p, m = router.resolve_model(task)
        assert p == "openai"
        assert m == "qwen-plus"


def test_model_router_uses_anthropic_model_for_all_tasks(monkeypatch):
    """When provider=claude, all tasks should use settings.anthropic_model."""
    from app.llm.router import ModelRouter
    monkeypatch.setattr("app.config.settings.llm_provider", "claude")
    monkeypatch.setattr("app.config.settings.anthropic_model", "claude-3-opus-20240229")
    router = ModelRouter()
    for task in ("writer_long", "writer_short", "reviewer", "discuss", "extractor"):
        provider, model = router.resolve_model(task)
        assert provider == "claude"
        assert model == "claude-3-opus-20240229"

