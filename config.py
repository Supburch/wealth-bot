import json

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings loaded from environment variables and ``.env``.

    Holds secrets and identity used at runtime (LINE credentials, Google
    service-account JSON, spreadsheet ids). Structural sheet config that needs
    to be injectable for tests lives in ``core.sheet_config.AppConfig`` — kept
    separate so repositories receive it via constructor (dependency injection)
    without depending on secrets.
    """

    LINE_CHANNEL_SECRET: str = Field(min_length=1)
    LINE_CHANNEL_ACCESS_TOKEN: str = Field(min_length=1)
    GOOGLE_CREDENTIALS_JSON: str = Field(min_length=1)
    MASTER_SPREADSHEET_ID: str = ""
    SPREADSHEET_ID: str = ""

    APP_VERSION: str = "1.0.0"

    @field_validator("GOOGLE_CREDENTIALS_JSON")
    @classmethod
    def validate_google_credentials(cls, value: str) -> str:
        """Fail fast on a malformed or non-service-account credentials JSON."""
        try:
            data = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"GOOGLE_CREDENTIALS_JSON is not valid JSON: {exc}") from exc
        if data.get("type") != "service_account" or not data.get("private_key"):
            raise ValueError(
                "GOOGLE_CREDENTIALS_JSON must be a service-account key "
                "(type='service_account' with a private_key)"
            )
        return value

    @model_validator(mode='after')
    def validate_critical_settings(self) -> 'Settings':
        if not self.MASTER_SPREADSHEET_ID:
            self.MASTER_SPREADSHEET_ID = self.SPREADSHEET_ID
        if not self.MASTER_SPREADSHEET_ID:
            raise ValueError("Startup Error: MASTER_SPREADSHEET_ID must be set")
        return self

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
