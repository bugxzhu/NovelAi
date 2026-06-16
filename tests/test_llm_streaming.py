from unittest.mock import MagicMock

from app.llm.base import LLMRequest
from app.llm.providers.claude import ClaudeProvider
from app.llm.router import ModelRouter
from app.llm.streaming import StreamEvent


def test_stream_event_token():
    e = StreamEvent(type="token", text="hi")
    assert e.type == "token"
    assert e.text == "hi"
    assert e.input_tokens == 0


def test_stream_event_done_defaults():
    e = StreamEvent(type="done", input_tokens=10, output_tokens=5, stop_reason="end_turn")
    assert e.type == "done"
    assert e.error_message == ""


def test_claude_stream_yields_tokens_then_done(monkeypatch):
    fake_stream_obj = MagicMock()
    fake_stream_obj.text_stream = iter(["Hello ", "world"])
    fake_final = MagicMock()
    fake_final.usage.input_tokens = 10
    fake_final.usage.output_tokens = 3
    fake_final.stop_reason = "end_turn"
    fake_stream_obj.get_final_message.return_value = fake_final

    fake_client = MagicMock()
    fake_client.messages.stream.return_value.__enter__.return_value = fake_stream_obj
    monkeypatch.setattr("app.llm.providers.claude.Anthropic", lambda **kw: fake_client)

    provider = ClaudeProvider(api_key="fake")
    events = list(provider.stream(
        LLMRequest(model_task="writer_long", user="hi"),
        "claude-sonnet-4-6",
    ))

    types = [e.type for e in events]
    assert types == ["token", "token", "done"]
    assert "".join(e.text for e in events if e.type == "token") == "Hello world"
    done = events[-1]
    assert done.input_tokens == 10
    assert done.output_tokens == 3
    assert done.stop_reason == "end_turn"
    call_kwargs = fake_client.messages.stream.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert call_kwargs["messages"] == [{"role": "user", "content": "hi"}]


def test_claude_stream_includes_system_when_set(monkeypatch):
    fake_stream_obj = MagicMock()
    fake_stream_obj.text_stream = iter(["ok"])
    fake_final = MagicMock()
    fake_final.usage.input_tokens = 1
    fake_final.usage.output_tokens = 1
    fake_final.stop_reason = "end_turn"
    fake_stream_obj.get_final_message.return_value = fake_final

    fake_client = MagicMock()
    fake_client.messages.stream.return_value.__enter__.return_value = fake_stream_obj
    monkeypatch.setattr("app.llm.providers.claude.Anthropic", lambda **kw: fake_client)

    provider = ClaudeProvider(api_key="fake")
    list(provider.stream(
        LLMRequest(model_task="writer_long", user="hi", system="You are X"),
        "claude-sonnet-4-6",
    ))
    call_kwargs = fake_client.messages.stream.call_args.kwargs
    assert call_kwargs["system"] == "You are X"


def test_claude_stream_wraps_errors(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.stream.side_effect = RuntimeError("API down")
    monkeypatch.setattr("app.llm.providers.claude.Anthropic", lambda **kw: fake_client)

    provider = ClaudeProvider(api_key="fake")
    events = list(provider.stream(
        LLMRequest(model_task="writer_long", user="hi"),
        "claude-sonnet-4-6",
    ))
    assert len(events) == 1
    assert events[0].type == "error"
    assert "API down" in events[0].error_message
    assert events[0].error_code == "RuntimeError"


def test_model_router_stream_forwards(monkeypatch):
    """ModelRouter.stream yields from the resolved provider's stream."""
    fake_provider = MagicMock()
    fake_provider.stream.return_value = iter([
        StreamEvent(type="token", text="a"),
        StreamEvent(type="done", input_tokens=1, output_tokens=1, stop_reason="end_turn"),
    ])
    router = ModelRouter()
    monkeypatch.setattr(router, "_providers", {"claude": fake_provider})

    events = list(router.stream(LLMRequest(model_task="writer_long", user="x")))
    assert [e.type for e in events] == ["token", "done"]
    fake_provider.stream.assert_called_once()
    args, kwargs = fake_provider.stream.call_args
    # First positional arg is request, second is model
    assert args[1] == "claude-sonnet-4-6" or kwargs.get("model") == "claude-sonnet-4-6"
