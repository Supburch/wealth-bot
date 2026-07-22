from pydantic_settings import BaseSettings, SettingsConfigDict

class AppConfig(BaseSettings):
    portfolio_range: str = "Portfolio!A2:D"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
