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

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
