from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    openrouter_api_key: str
    # OpenRouter model ids, comma-separated, tried in order (later ones are fallbacks)
    vision_models: str = "anthropic/claude-haiku-5.5,qwen/qwen3.8-flash"
    upload_dir: str = "uploads"

    @property
    def vision_model_list(self) -> list[str]:
        return [m.strip() for m in self.vision_models.split(",") if m.strip()]


settings = Settings()
