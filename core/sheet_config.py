from pydantic_settings import BaseSettings, SettingsConfigDict

class AppConfig(BaseSettings):
    portfolio_range: str = "Portfolio!A2:D"
    validation_result_sheet: str = "ValidationResult"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
