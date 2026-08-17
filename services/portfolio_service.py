"""
portfolio_service.py

Two access patterns co-exist in this module:

1. Class-based PortfolioService
   Reads the raw Portfolio sheet via PortfolioRepository and builds
   PortfolioHoldings (domain model).  Used by PortfolioHandler.

2. Module-level async functions
   Read pre-computed summary sheets (PortfolioSummary, TodaySummary,
   HoldingsBreakdown, AssetAllocation) and return presentation DTOs.
   Used by the new handler-based architecture.
"""
import asyncio
import logging
from decimal import Decimal, InvalidOperation
from enum import IntEnum
from typing import Generic, TypeVar

from pydantic import ValidationError

from core.exceptions import PortfolioParseError, PortfolioReadError
from core.messages import PORTFOLIO_PARSE_ERROR, PORTFOLIO_READ_ERROR
from models.portfolio import (
    HoldingBreakdown,
    PortfolioHoldings,
    PortfolioItem,
    PortfolioRow,
    PortfolioSummary,
    TodaySummary,
    WealthSummary,
)
from models.user import UserInfo
from repositories.portfolio_repository import PortfolioRepository
from services.cache import cached
from services.sheets_service import get_sheet_as_dict, get_sheet_records

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ── Helpers ────────────────────────────────────────────────────────────────────

class ServiceResult(Generic[T]):
    """Lightweight result/error wrapper used by PortfolioService."""

    def __init__(self, data: T | None = None, error: str | None = None):
        self.data = data
        self.error = error

    @property
    def is_success(self) -> bool:
        return self.error is None


class PortfolioColumn(IntEnum):
    SYMBOL = 0
    AVG_COST = 1
    SHARES = 2
    CURRENT_PRICE = 3


def _parse_float(value: object) -> float:
    """Strip commas, currency symbols, percent signs, and convert to float."""
    clean_val = str(value).replace(",", "").replace("฿", "").replace("$", "").replace("%", "").strip()
    if not clean_val:
        return 0.0
    return float(clean_val)



# ── Class-based PortfolioService (domain) ─────────────────────────────────────

class PortfolioService:
    """Builds PortfolioHoldings from raw Portfolio sheet via PortfolioRepository."""

    def __init__(self, repository: PortfolioRepository):
        self.repository = repository

    def get_portfolio(
        self, spreadsheet_id: str, strict: bool = False
    ) -> ServiceResult[PortfolioHoldings]:
        try:
            rows = self.repository.fetch_portfolio_rows(spreadsheet_id)
            items: list[PortfolioItem] = []

            for row in rows:
                try:
                    item = PortfolioItem(
                        symbol=row.symbol,
                        avg_cost=Decimal(row.avg_cost.replace(",", "")),
                        shares=Decimal(row.shares.replace(",", "")),
                        current_price=Decimal(row.current_price.replace(",", "")),
                    )
                    items.append(item)
                except (InvalidOperation, ValidationError, ValueError) as e:
                    logger.warning(
                        "Skipping invalid row",
                        extra={"error_type": type(e).__name__},
                    )
                    if strict:
                        raise PortfolioParseError(
                            f"Error parsing row for symbol {row.symbol}: {e}"
                        ) from e

            return ServiceResult(data=PortfolioHoldings(items=items))

        except PortfolioReadError:
            return ServiceResult(error=PORTFOLIO_READ_ERROR)
        except PortfolioParseError:
            return ServiceResult(error=PORTFOLIO_PARSE_ERROR)
        except Exception:
            logger.exception("Unexpected error in PortfolioService.get_portfolio")
            return ServiceResult(error="Internal service error")


# ── Module-level async functions (presentation DTOs) ──────────────────────────

@cached("portfolio_summary")
async def get_portfolio_summary(user_info: UserInfo) -> PortfolioSummary:
    """Read pre-computed summary from 'PortfolioSummary' sheet (Metric|Value format)."""
    data = await asyncio.to_thread(get_sheet_as_dict, user_info.spreadsheet_id, "PortfolioSummary")
    return PortfolioSummary(
        portfolio_value=_parse_float(data["PortfolioValue"]),
        cost_basis=_parse_float(data["CostBasis"]),
        profit=_parse_float(data["Profit"]),
        profit_pct=_parse_float(data["ProfitPct"]),
        cash=_parse_float(data["Cash"]),
    )


@cached("today_summary")
async def get_today_summary(user_info: UserInfo) -> TodaySummary:
    """Read pre-computed summary from 'TodaySummary' sheet (Metric|Value format)."""
    data = await asyncio.to_thread(get_sheet_as_dict, user_info.spreadsheet_id, "TodaySummary")
    return TodaySummary(
        portfolio_value=_parse_float(data["PortfolioValue"]),
        today_profit=_parse_float(data["TodayProfit"]),
        today_profit_pct=_parse_float(data["TodayProfitPct"]),
    )


@cached("holdings_index")
async def _fetch_holdings_index(user_info: UserInfo) -> dict[str, HoldingBreakdown]:
    """
    Fetch HoldingsBreakdown records and build an uppercase-symbol → HoldingBreakdown dict.
    Cached per user for O(1) symbol lookup.
    """
    records = await asyncio.to_thread(get_sheet_records, user_info.spreadsheet_id, "HoldingsBreakdown")
    index: dict[str, HoldingBreakdown] = {}
    for row in records:
        symbol = str(row.get("Symbol", "")).strip().upper()
        if not symbol:
            continue
        try:
            index[symbol] = HoldingBreakdown(
                symbol=symbol,
                market_value=_parse_float(row.get("MarketValue", "0")),
                weight=_parse_float(row.get("Weight", "0")),
                cost=_parse_float(row.get("Cost", "0")),
                profit_pct=_parse_float(row.get("ProfitPct", "0")),
            )
        except (ValueError, KeyError) as e:
            logger.warning(
                "Skipping invalid holding row",
                extra={"error_type": type(e).__name__},
            )
    return index


async def get_all_holdings(user_info: UserInfo) -> list[HoldingBreakdown]:
    """Return all holdings from the cached index."""
    index = await _fetch_holdings_index(user_info)
    return list(index.values())


async def get_top_holdings(user_info: UserInfo) -> list[HoldingBreakdown]:
    """Return all holdings sorted by weight descending."""
    holdings = await get_all_holdings(user_info)
    return sorted(holdings, key=lambda h: h.weight, reverse=True)


async def get_holding_breakdown(
    user_info: UserInfo, symbol: str
) -> HoldingBreakdown | None:
    """O(1) lookup of a single holding by symbol (case-insensitive)."""
    index = await _fetch_holdings_index(user_info)
    return index.get(symbol.upper())


async def get_wealth_summary(user_info: UserInfo) -> WealthSummary:
    """Composite: portfolio summary + top 3 holdings."""
    summary = await get_portfolio_summary(user_info)
    top_holdings = await get_top_holdings(user_info)
    return WealthSummary(summary=summary, top_holdings=top_holdings[:3])


@cached("asset_allocation")
async def get_asset_allocation(user_info: UserInfo) -> dict[str, Decimal]:
    """
    Read from 'AssetAllocation' sheet (Metric|Value format).
    Returns dict[str, Decimal] placeholder until the sheet schema is confirmed.
    """
    data = await asyncio.to_thread(get_sheet_as_dict, user_info.spreadsheet_id, "AssetAllocation")
    result: dict[str, Decimal] = {}
    for k, v in data.items():
        try:
            result[k] = Decimal(str(v).replace(",", "").strip())
        except Exception:
            logger.warning("Skipping invalid allocation entry")
    return result

