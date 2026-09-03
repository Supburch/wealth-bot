"""
Portfolio models.

Organized in two groups:

  Domain Models — derived from raw sheet data, used by PortfolioService:
      PortfolioRow, PortfolioItem, PortfolioHoldings

  Presentation DTOs — flat structs read from pre-computed summary sheets,
      used by module-level service functions and LINE reply formatters:
      PortfolioSummary, TodaySummary, HoldingBreakdown, WealthSummary
"""
from decimal import Decimal
from pydantic import BaseModel, model_validator
from core.constants import TWOPLACES


# ── Domain Models ──────────────────────────────────────────────────────────────

class PortfolioRow(BaseModel):
    """Raw string row fetched from the Portfolio sheet."""
    symbol: str
    avg_cost: str
    shares: str
    current_price: str


class PortfolioItem(BaseModel):
    """Parsed position with computed financial properties."""
    symbol: str
    avg_cost: Decimal
    shares: Decimal
    current_price: Decimal

    @model_validator(mode="after")
    def validate_positive_values(self) -> "PortfolioItem":
        if self.shares < 0:
            raise ValueError(f"Shares cannot be negative for {self.symbol}")
        if self.avg_cost < 0 or self.current_price < 0:
            raise ValueError(f"Prices cannot be negative for {self.symbol}")
        return self

    @property
    def market_value(self) -> Decimal:
        return (self.shares * self.current_price).quantize(TWOPLACES)

    @property
    def total_cost(self) -> Decimal:
        return (self.shares * self.avg_cost).quantize(TWOPLACES)

    @property
    def profit(self) -> Decimal:
        return self.market_value - self.total_cost


class PortfolioHoldings(BaseModel):
    """
    Aggregate collection of PortfolioItems computed from the raw Portfolio sheet.
    (Renamed from PortfolioSummary to avoid naming conflict with the presentation DTO.)
    """
    items: list[PortfolioItem]

    @property
    def total_market_value(self) -> Decimal:
        return sum((item.market_value for item in self.items), Decimal("0.00"))

    @property
    def total_cost(self) -> Decimal:
        return sum((item.total_cost for item in self.items), Decimal("0.00"))

    @property
    def total_profit(self) -> Decimal:
        return self.total_market_value - self.total_cost

    @property
    def roi_percent(self) -> Decimal:
        if self.total_cost == 0:
            return Decimal("0.00")
        return ((self.total_profit / self.total_cost) * 100).quantize(TWOPLACES)

    @property
    def total_positions(self) -> int:
        return len(self.items)

    @property
    def is_empty(self) -> bool:
        return len(self.items) == 0


# ── Presentation / Response DTOs ───────────────────────────────────────────────

class PortfolioSummary(BaseModel):
    """
    Pre-computed flat summary read from the 'PortfolioSummary' sheet (Metric|Value format).
    Used by module-level service functions and LINE reply formatters.
    """
    portfolio_value: float
    cost_basis: float
    profit: float
    profit_pct: float
    cash: float


class TodaySummary(BaseModel):
    """Pre-computed today's performance read from the 'TodaySummary' sheet."""
    portfolio_value: float
    today_profit: float
    today_profit_pct: float


class HoldingBreakdown(BaseModel):
    """
    Single holding derived from the raw 'Portfolio' sheet (USD), converted to
    THB using the AssetAllocation FX rate. market_value and cost are in THB;
    weight and profit_pct are currency-agnostic ratios.
    Indexed by uppercase symbol for O(1) lookup when cached as a dict.
    """
    symbol: str
    market_value: float
    weight: float
    cost: float
    profit_pct: float


class AssetAllocationEntry(BaseModel):
    """Single asset class: raw value plus its computed portfolio weight."""

    name: str
    value: Decimal
    percent: Decimal


class AssetAllocation(BaseModel):
    """
    Aggregate asset allocation computed from the 'AssetAllocation' sheet.

    The sheet stores one row per asset class in ``Type | Value`` format, so
    adding a new asset type is just a new row — no code change required.
    Percentages are derived here from the raw values.
    """

    entries: list[AssetAllocationEntry]

    @property
    def total(self) -> Decimal:
        return sum((e.value for e in self.entries), Decimal("0")).quantize(TWOPLACES)

    @property
    def total_percent(self) -> Decimal:
        return sum((e.percent for e in self.entries), Decimal("0"))

    @property
    def is_empty(self) -> bool:
        return len(self.entries) == 0


class WealthSummary(BaseModel):
    """
    Composite presentation DTO: portfolio summary + top holdings + allocation.
    asset_allocation is None when no allocation data could be read.
    """

    summary: PortfolioSummary
    top_holdings: list[HoldingBreakdown]
    asset_allocation: AssetAllocation | None = None
    best_performer: str | None = None
    worst_performer: str | None = None
