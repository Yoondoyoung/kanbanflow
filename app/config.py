from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./kanbanflow.db"
    session_secret: str = "dev-insecure-secret-change-me"
    secure_cookies: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
