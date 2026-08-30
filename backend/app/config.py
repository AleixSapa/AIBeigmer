from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./aibeigmer.db"
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None
    anthropic_api_key: str | None = None
    deepseek_api_key: str | None = None
    openrouter_api_key: str | None = None
    groq_api_key: str | None = None
    freellmapi_api_key: str | None = None
    freellmapi_base_url: str = "https://freellmapi.co/v1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
