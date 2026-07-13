from pydantic_settings import BaseSettings
from pydantic import model_validator

class Settings(BaseSettings):
    LINE_CHANNEL_SECRET: str
    LINE_CHANNEL_ACCESS_TOKEN: str

    GOOGLE_CREDENTIALS_JSON: str
    SPREADSHEET_ID: str

    ALLOWED_USERS: str
    ADMIN_USERS: str
    
    APP_VERSION: str = "1.0.0"

    @property
    def allowed_users_set(self) -> set[str]:
        return {user.strip() for user in self.ALLOWED_USERS.split(",") if user.strip()}
        
    @property
    def admin_users_set(self) -> set[str]:
        return {user.strip() for user in self.ADMIN_USERS.split(",") if user.strip()}

    @model_validator(mode='after')
    def validate_critical_settings(self) -> 'Settings':
        if not self.allowed_users_set:
            raise ValueError("Startup Error: ALLOWED_USERS ต้องมีอย่างน้อย 1 User ID")
        return self

    model_config = {"env_file": ".env"}

settings = Settings()
