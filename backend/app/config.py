from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


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
    record_fixtures: bool = Field(default=False, alias="OPL_RECORD_FIXTURES")
    fixtures_dir: Path = _BACKEND_ROOT / "tests" / "fixtures" / "api"
    spend_cap_usd: float = 25.0
    spend_ledger_file: str = "model_api_spend.jsonl"
    model_api_timeout_s: float = 60.0
    model_api_max_attempts: int = 4
    model_api_retry_after_max_s: float = 30.0
    prompt_cache_name: str = "orphan-parts"
    extract_reasoning_effort: str = "low"
    image_max_px: int = 1280
    max_photos: int = 4
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
        if self.model_api_max_attempts < 1:
            raise ValueError("MODEL_API_MAX_ATTEMPTS must be at least 1")
        if self.spend_cap_usd < 0:
            raise ValueError("SPEND_CAP_USD must not be negative")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def model_api_mode(self) -> str:
        if self.fake_api:
            return "fixture"
        return "record" if self.record_fixtures else "live"

    @property
    def spend_ledger_path(self) -> Path:
        return self.data_dir / self.spend_ledger_file


@lru_cache
def get_settings() -> Settings:
    return Settings()
