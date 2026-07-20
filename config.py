from pydantic_settings import BaseSettings
from pydantic import model_validator

class Settings(BaseSettings):
    LINE_CHANNEL_SECRET: str
    LINE_CHANNEL_ACCESS_TOKEN: str
    GOOGLE_CREDENTIALS_JSON: str
    MASTER_SPREADSHEET_ID: str = ""
    SPREADSHEET_ID: str = ""

    APP_VERSION: str = "1.0.0"

    @model_validator(mode='after')
    def validate_critical_settings(self) -> 'Settings':
        if not self.MASTER_SPREADSHEET_ID:
            self.MASTER_SPREADSHEET_ID = self.SPREADSHEET_ID
        if not self.MASTER_SPREADSHEET_ID:
            raise ValueError("Startup Error: MASTER_SPREADSHEET_ID must be set")
        return self

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
