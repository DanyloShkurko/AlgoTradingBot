import base64
import hashlib

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+psycopg2://algobot:algobot@localhost:5432/algobot"

    # Auth
    jwt_secret: str = "dev-insecure-jwt-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7

    # Encryption for stored Binance secrets (Fernet). Provide a full Fernet key
    # via ENCRYPTION_KEY in production; otherwise it is derived from a passphrase.
    encryption_key: str = ""
    encryption_passphrase: str = "dev-insecure-change-me"

    # Comma-separated list of allowed browser origins for CORS.
    cors_origins: str = "http://localhost:5173"

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def fernet_key(self) -> bytes:
        if self.encryption_key:
            return self.encryption_key.encode()
        digest = hashlib.sha256(self.encryption_passphrase.encode()).digest()
        return base64.urlsafe_b64encode(digest)


settings = Settings()
