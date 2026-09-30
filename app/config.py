from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="HEATZYD_", extra="ignore"
    )

    database_path: str = "data/heatzyd.db"
    heatzy_region: str = "EU"
    use_tls: bool = True
    tz: str | None = None  # None = system
    log_level: str = "INFO"

    retry_backoff_base: int = 15
    retry_backoff_cap: int = 240
    retry_max_attempts: int = 5


settings = Settings()
