from unittest.mock import MagicMock

import pytest

from app.llm.providers.openai import OpenAIProvider
from app.llm.providers.claude import ClaudeProvider


def test_openai_provider_embed_returns_vectors(monkeypatch):
    """embed() should call OpenAI embeddings endpoint and return list[list[float]]."""
    fake_client = MagicMock()
    fake_data = MagicMock()
    fake_data.embedding = [0.1, 0.2, 0.3]
    fake_client.embeddings.create.return_value = MagicMock(data=[fake_data, fake_data])

    provider = OpenAIProvider(api_key="fake")
    provider._client = fake_client  # bypass constructor

    result = provider.embed(["hello", "world"], "text-embedding-3-small")
    assert len(result) == 2
    assert result[0] == [0.1, 0.2, 0.3]
    fake_client.embeddings.create.assert_called_once_with(
        model="text-embedding-3-small", input=["hello", "world"]
    )


def test_claude_provider_embed_raises_not_implemented():
    """Claude has no embeddings API; raise NotImplementedError."""
    provider = ClaudeProvider(api_key="fake")
    with pytest.raises(NotImplementedError):
        provider.embed(["hello"], "any-model")
