from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    model_api_key: SecretStr | None = None
    model_api_base_url: str = "https://api.meta.ai/v1"

    model_spark: str = "muse-spark-1.3"
    model_wonder: str = "muse-wonder-1.0"
    model_image: str = "muse-image-1.0"
    model_voice: str = "muse-voice-transcribe-1.0"
    model_sam: str = "sam-3.1"

    fake_api: bool = Field(default=False, alias="OPL_FAKE_API")
    spend_cap_usd: float = 25.0
    retention_hours: int = 24
    cors_origins: str = "http://localhost:5173"
    data_dir: Path = Path("./data")
    max_upload_mb: int = 12

    log_format: str = "json"
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _need_key_unless_fake(self) -> Self:
        # Fail at startup, not on the first user request.
        if not self.fake_api and not (self.model_api_key and self.model_api_key.get_secret_value()):
            raise ValueError("MODEL_API_KEY is empty; set it or run with OPL_FAKE_API=1")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def model_api_mode(self) -> str:
        return "fixture" if self.fake_api else "live"


@lru_cache
def get_settings() -> Settings:
    return Settings()
