from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Async Document Processing Workflow System"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg2://postgres:postgres@postgres:5432/docflow"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    uploads_dir: str = "uploads"
    max_file_size_mb: int = 20
    max_files_per_upload: int = 3
    cors_origins: str = "http://localhost:3000,http://localhost:3001"
    cors_allow_origin_regex: str | None = r"https://.*\.vercel\.app"


settings = Settings()
