import logging
from services.sheets_service import get_sheet_as_dict, get_sheet_records
from services.cache import cached
from models.portfolio import (
    PortfolioSummary, TodaySummary, AssetAllocation,
    HoldingBreakdown, WealthSummary
)

logger = logging.getLogger(__name__)


@cached("portfolio_summary")
async def get_portfolio_summary() -> PortfolioSummary:
    data = get_sheet_as_dict("PortfolioSummary")
    return PortfolioSummary(
        portfolio_value=float(data.get("PortfolioValue", 0)),
        cost_basis=float(data.get("CostBasis", 0)),
        profit=float(data.get("Profit", 0)),
        profit_pct=float(data.get("ProfitPct", 0)),
        cash=float(data.get("Cash", 0)),
    )


@cached("today_summary")
async def get_today_summary() -> TodaySummary:
    data = get_sheet_as_dict("TodaySummary")
    return TodaySummary(
        portfolio_value=float(data.get("PortfolioValue", 0)),
        today_profit=float(data.get("TodayProfit", 0)),
        today_profit_pct=float(data.get("TodayProfitPct", 0)),
    )


@cached("asset_allocation")
async def get_allocation() -> list[AssetAllocation]:
    records = get_sheet_records("AssetAllocation")
    return [
        AssetAllocation(asset_class=r["AssetClass"], percent=float(r["Percent"]))
        for r in records
    ]


@cached("holdings_breakdown")
async def _fetch_holdings_data() -> tuple[list[HoldingBreakdown], dict[str, HoldingBreakdown]]:
    """Fetch holdings from Sheets and build an O(1) symbol index in one pass."""
    records = get_sheet_records("HoldingsBreakdown")
    holdings = [
        HoldingBreakdown(
            symbol=r["Symbol"],
            market_value=float(r["MarketValue"]),
            weight=float(r["Weight"]),
            cost=float(r["Cost"]),
            profit_pct=float(r["ProfitPct"]),
        )
        for r in records
    ]
    # Build uppercase index once — lookups after cache warm are O(1)
    index: dict[str, HoldingBreakdown] = {h.symbol.upper(): h for h in holdings}
    return holdings, index


async def get_all_holdings() -> list[HoldingBreakdown]:
    holdings, _ = await _fetch_holdings_data()
    return holdings


async def get_holding_breakdown(symbol: str) -> HoldingBreakdown | None:
    """O(1) lookup via cached symbol index."""
    _, index = await _fetch_holdings_data()
    return index.get(symbol.upper())


async def get_top_holdings() -> list[HoldingBreakdown]:
    holdings = await get_all_holdings()
    return sorted(holdings, key=lambda h: h.weight, reverse=True)


async def get_wealth_summary() -> WealthSummary:
    summary = await get_portfolio_summary()
    top_holdings = await get_top_holdings()
    return WealthSummary(summary=summary, top_holdings=top_holdings)
