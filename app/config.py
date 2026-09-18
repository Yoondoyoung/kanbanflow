from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./kanbanflow.db"
    session_secret: str = "dev-insecure-secret-change-me"
    secure_cookies: bool = False
    allowed_origins: list[str] = ["http://localhost:8000"]
    github_app_id: str | None = None
    github_app_slug: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_private_key: str | None = None
    github_webhook_secret: str | None = None
    github_api_url: str = "https://api.github.com"
    github_web_url: str = "https://github.com"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
