from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOVELAI_", env_file=".env", extra="ignore")

    db_path: Path = Path("./data/novelai.db")
    host: str = "127.0.0.1"
    port: int = 8000
    # ANTHROPIC_API_KEY 没有 NOVELAI_ 前缀；AliasChoices 让它既能从无前缀的 env 读取，
    # 也兼容 NOVELAI_ANTHROPIC_API_KEY 形式
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "NOVELAI_ANTHROPIC_API_KEY"),
    )
    anthropic_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("ANTHROPIC_BASE_URL", "NOVELAI_ANTHROPIC_BASE_URL"),
    )
    anthropic_model: str = Field(
        default="claude-sonnet-4-6",
        validation_alias=AliasChoices("ANTHROPIC_MODEL", "NOVELAI_ANTHROPIC_MODEL"),
    )

    # LLM provider selection: "claude" or "openai"
    # Reads NOVELAI_LLM_PROVIDER (field name without "default_" prefix is intentional
    # for a concise env var name).
    llm_provider: str = "claude"

    # OpenAI-compatible settings (works with OpenAI / DashScope / Ollama / vLLM / etc.)
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_API_KEY", "NOVELAI_OPENAI_API_KEY"),
    )
    openai_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_BASE_URL", "NOVELAI_OPENAI_BASE_URL"),
    )
    # Single model used for all tasks (keep config simple; can split later)
    openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_MODEL", "NOVELAI_OPENAI_MODEL"),
    )

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
