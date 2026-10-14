from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    allowed_origins: str = ""
    rate_limit_login: str = "5/minute"
    rate_limit_register: str = "3/minute"
    bootstrap_admin_email: str = ""
    bootstrap_admin_username: str = ""
    bootstrap_admin_password: str = ""
    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]
settings = Settings()
