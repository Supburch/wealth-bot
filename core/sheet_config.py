from pydantic_settings import BaseSettings, SettingsConfigDict

class AppConfig(BaseSettings):
    portfolio_range: str = "Portfolio!A2:D"
    dr_range: str = "from Streaming-DR!A2:N200"
    validation_result_sheet: str = "ValidationResult"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Drill-down breakdowns: category → source sheet/range (B=name, C=value per row).
# Ranges are generous (e.g. A1:C50); parsing stops at the first blank row, so new
# sub-items can be added without editing code. Add an entry here to enable the
# 🔍 quick-reply button for another category.
ASSET_BREAKDOWN_RANGES: dict[str, dict[str, str]] = {
    "Retirement Savings": {
        "sheet": "from Sum Wealth",
        "range": "A1:C50",
    },
}


def resolve_breakdown_category(category: str) -> str | None:
    """Case-insensitive lookup of a breakdown category; returns the canonical name."""
    for name in ASSET_BREAKDOWN_RANGES:
        if name.casefold() == category.casefold():
            return name
    return None
