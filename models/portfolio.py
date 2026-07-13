from pydantic import BaseModel


class PortfolioSummary(BaseModel):
    portfolio_value: float
    cost_basis: float
    profit: float
    profit_pct: float
    cash: float


class TodaySummary(BaseModel):
    portfolio_value: float
    today_profit: float
    today_profit_pct: float


class AssetAllocation(BaseModel):
    asset_class: str
    percent: float


class HoldingBreakdown(BaseModel):
    symbol: str
    market_value: float
    weight: float
    cost: float
    profit_pct: float


class WealthSummary(BaseModel):
    summary: PortfolioSummary
    top_holdings: list[HoldingBreakdown]
