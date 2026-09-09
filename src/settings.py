from pydantic_settings import BaseSettings, SettingsConfigDict
from paths import PROJECT_ROOT


class Settings(BaseSettings):
    # Required — app fails fast at startup with a clear error if these are
    # missing, instead of failing confusingly deep inside an API call later.
    anthropic_api_key: str
    voyage_api_key: str

    # Optional, with a sensible local-dev default.
    allowed_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_origins_list(self) -> list[str]:
        """ALLOWED_ORIGINS is a comma-separated string in .env (e.g. for
        multiple frontend URLs); this splits it into a clean list on demand.
        """
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


# Single shared instance, imported everywhere config is needed — same
# "one source of truth" pattern as paths.py, just for settings instead of
# file locations. Reading env vars happens once, here, at import time.
settings = Settings()