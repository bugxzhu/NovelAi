from unittest.mock import MagicMock


def test_router_embed_delegates_to_provider():
    """Router.embed should call the resolved provider's embed with configured model."""
    from app.llm.router import ModelRouter

    fake_provider = MagicMock()
    fake_provider.embed.return_value = [[0.1, 0.2], [0.3, 0.4]]

    router = ModelRouter()
    router._providers = {"openai": fake_provider}

    result = router.embed(["hello", "world"], "text-embedding-3-small")
    assert result == [[0.1, 0.2], [0.3, 0.4]]
    fake_provider.embed.assert_called_once_with(["hello", "world"], "text-embedding-3-small")


def test_router_embed_defaults_model_from_settings():
    """If model is None, router falls back to settings.embedding_model."""
    from app.llm.router import ModelRouter

    fake_provider = MagicMock()
    fake_provider.embed.return_value = [[0.1]]

    router = ModelRouter()
    router._providers = {"openai": fake_provider}

    router.embed(["x"])
    args = fake_provider.embed.call_args
    assert args[0][1] is not None
