import re
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

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
    key_probe: bool = Field(default=True, alias="OPL_KEY_PROBE")
    fixtures_dir: Path = _BACKEND_ROOT / "tests" / "fixtures" / "api"
    spend_cap_usd: float = 25.0
    spend_ledger_file: str = "model_api_spend.jsonl"
    model_api_timeout_s: float = 60.0
    model_api_max_attempts: int = 4
    model_api_retry_after_max_s: float = 30.0
    prompt_cache_name: str = "orphan-parts"
    extract_reasoning_effort: str = "low"
    image_max_px: int = 1280
    segment_max_px: int = 800
    voice_max_seconds: int = 600
    price_search_context: Literal["low", "medium", "high"] = "low"
    price_country: str = ""
    marketplace_create_url: str = "https://www.facebook.com/marketplace/create/item"
    marketplace_search_url: str = "https://www.facebook.com/marketplace/search/"
    candidate_days: int = 14
    # the demo gate: empty code = no gate (a machine of your own); set it on any host others reach
    demo_access_code: SecretStr | None = None
    demo_session_hours: int = 12
    demo_visitor_calls_per_hour: int = 20
    demo_daily_calls: int = 300
    demo_code_attempts: int = 5
    demo_requests_per_minute: int = 120
    demo_paused: bool = False
    demo_trust_proxy: bool = False
    demo_cookie_secure: bool = False
    # the session a pairing QR carries lasts minutes: long enough to scan and claim
    pair_token_minutes: int = 15
    # how long the code a phone gets on its first scan lasts; never past the code that paired it
    pair_code_days: int = 30
    max_photos: int = 4
    # a picture of what an item could become, drawn by Muse Image on a click: off unless set,
    # since every click is a paid call
    picture_enabled: bool = False
    retention_hours: int = 24
    cors_origins: str = "http://localhost:5173"
    data_dir: Path = Path("./data")
    # WAL needs shared memory between the connections, which a network filesystem
    # cannot give; DELETE there (Modal's volume sets it)
    sqlite_journal_mode: Literal["WAL", "DELETE", "TRUNCATE"] = "WAL"
    max_upload_mb: int = 12
    extract_enhance: bool = True
    extract_blur_threshold: float = 150.0
    max_clip_mb: int = 60
    max_captures: int = 200
    inventory_db_file: str = "inventory.sqlite3"
    # measurement captures: what a photo must give before a number is computed from it
    measure_min_sharpness: float = 150.0
    measure_min_reference_px: int = 80
    measure_min_image_px: int = 480
    measure_mark_px: float = 1.5

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
        if self.price_country and not re.fullmatch(r"[A-Z]{2}", self.price_country):
            raise ValueError("PRICE_COUNTRY must be a two-letter ISO 3166-1 code, or empty")
        if self.candidate_days < 1:
            raise ValueError("CANDIDATE_DAYS must be at least 1")
        if "*" in self.cors_origin_list:
            # the browser sends credentials with every call; a wildcard would hand them to any site
            raise ValueError("CORS_ORIGINS must name the origins; * is not allowed")
        for name in (
            "demo_session_hours",
            "demo_visitor_calls_per_hour",
            "demo_daily_calls",
            "demo_code_attempts",
            "demo_requests_per_minute",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name.upper()} must be at least 1")
        for name, most in (("pair_token_minutes", 60), ("pair_code_days", 3650)):
            if not 1 <= getattr(self, name) <= most:
                raise ValueError(f"{name.upper()} must be between 1 and {most}")
        code = self.demo_access_code.get_secret_value() if self.demo_access_code else ""
        if code and len(code) < 12:
            raise ValueError("DEMO_ACCESS_CODE must be at least 12 characters")
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

    @property
    def inventory_db_path(self) -> Path:
        return self.data_dir / self.inventory_db_file


@lru_cache
def get_settings() -> Settings:
    return Settings()
