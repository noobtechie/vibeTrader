from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyUrl


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://trading:trading_secret@localhost:5432/trading_db"
    sync_database_url: str = "postgresql://trading:trading_secret@localhost:5432/trading_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Encryption (for brokerage tokens)
    encryption_key: str = "dev-secret-encrypt-key-123456789"

    # Environment
    environment: str = "development"
    debug: bool = True

    # CORS
    allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Questrade
    questrade_client_id: str = ""
    questrade_auth_url: str = "https://login.questrade.com/oauth2/token"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()
