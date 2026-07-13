from pydantic import BaseModel


class HealthDto(BaseModel):
    status: str
    google_sheets: str
    cache_entries: int
    uptime_seconds: int
    version: str
