import logging
from services.sheets_service import get_sheet_as_dict, get_sheet_records
from services.cache import cached
from models.portfolio import (
    PortfolioSummary, TodaySummary, AssetAllocation,
    HoldingBreakdown, WealthSummary
)
from models.user import UserInfo

logger = logging.getLogger(__name__)


@cached("portfolio_summary")
async def get_portfolio_summary(user_info: UserInfo) -> PortfolioSummary:
    data = get_sheet_as_dict(user_info.spreadsheet_id, "PortfolioSummary")
    return PortfolioSummary(
        portfolio_value=float(data.get("PortfolioValue", 0)),
        cost_basis=float(data.get("CostBasis", 0)),
        profit=float(data.get("Profit", 0)),
        profit_pct=float(data.get("ProfitPct", 0)),
        cash=float(data.get("Cash", 0)),
    )


@cached("today_summary")
async def get_today_summary(user_info: UserInfo) -> TodaySummary:
    data = get_sheet_as_dict(user_info.spreadsheet_id, "TodaySummary")
    return TodaySummary(
        portfolio_value=float(data.get("PortfolioValue", 0)),
        today_profit=float(data.get("TodayProfit", 0)),
        today_profit_pct=float(data.get("TodayProfitPct", 0)),
    )


@cached("asset_allocation")
async def get_allocation(user_info: UserInfo) -> list[AssetAllocation]:
    records = get_sheet_records(user_info.spreadsheet_id, "AssetAllocation")
    return [
        AssetAllocation(asset_class=r["AssetClass"], percent=float(r["Percent"]))
        for r in records
    ]


@cached("holdings_breakdown")
async def _fetch_holdings_data(user_info: UserInfo) -> tuple[list[HoldingBreakdown], dict[str, HoldingBreakdown]]:
    """Fetch holdings from Sheets and build an O(1) symbol index in one pass."""
    records = get_sheet_records(user_info.spreadsheet_id, "HoldingsBreakdown")
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


async def get_all_holdings(user_info: UserInfo) -> list[HoldingBreakdown]:
    holdings, _ = await _fetch_holdings_data(user_info)
    return holdings


async def get_holding_breakdown(user_info: UserInfo, symbol: str) -> HoldingBreakdown | None:
    """O(1) lookup via cached symbol index."""
    _, index = await _fetch_holdings_data(user_info)
    return index.get(symbol.upper())


async def get_top_holdings(user_info: UserInfo) -> list[HoldingBreakdown]:
    holdings = await get_all_holdings(user_info)
    return sorted(holdings, key=lambda h: h.weight, reverse=True)


async def get_wealth_summary(user_info: UserInfo) -> WealthSummary:
    summary = await get_portfolio_summary(user_info)
    top_holdings = await get_top_holdings(user_info)
    return WealthSummary(summary=summary, top_holdings=top_holdings)
