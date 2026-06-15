from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOVELAI_", env_file=".env", extra="ignore")

    db_path: Path = Path("./data/novelai.db")
    host: str = "127.0.0.1"
    port: int = 8000
    anthropic_api_key: str = ""

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
