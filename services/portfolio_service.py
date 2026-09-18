"""
portfolio_service.py

Two access patterns co-exist in this module:

1. Class-based PortfolioService
   Reads the raw Portfolio sheet via PortfolioRepository and builds
   PortfolioHoldings (domain model).  Used by PortfolioHandler.

2. Module-level async functions
   Read the authoritative AssetAllocation sheet and derive individual
   holdings from the raw Portfolio sheet. Returns presentation DTOs used
   by the handler-based architecture.
"""
import asyncio
import logging
from decimal import Decimal, InvalidOperation
from enum import IntEnum
from typing import Generic, TypeVar

from pydantic import ValidationError

from core.constants import TWOPLACES
from core.exceptions import PortfolioParseError, PortfolioReadError, SheetsReadError
from core.messages import DATA_UPDATING, PORTFOLIO_PARSE_ERROR, PORTFOLIO_READ_ERROR
from core.sheet_config import ASSET_BREAKDOWN_RANGES, resolve_breakdown_category
from models.portfolio import (
    AssetAllocation,
    AssetAllocationEntry,
    AssetBreakdown,
    AssetBreakdownItem,
    DrHolding,
    HoldingBreakdown,
    PortfolioHoldings,
    PortfolioItem,
    PortfolioResult,
    PortfolioRow,
)
from models.user import UserInfo
from repositories.portfolio_repository import PortfolioRepository
from services.cache import cached
from services.sheets_service import get_raw_range, get_sheet_as_dict, get_sheet_records

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
    """Strip commas, currency symbols, percent signs, and convert to float.

    Empty cells and spreadsheet error placeholders (e.g. ``#N/A``) resolve to
    ``0.0`` so a single unreadable cell can never crash the holdings index.
    """
    clean_val = str(value).replace(",", "").replace("฿", "").replace("$", "").replace("%", "").strip()
    if not clean_val:
        return 0.0
    try:
        return float(clean_val)
    except ValueError:
        return 0.0


def _is_numeric(value: object) -> bool:
    """Return True if ``value`` is blank or a plain number (after cleanup).

    Spreadsheet error placeholders such as ``#N/A`` are *not* numeric, which lets
    callers distinguish an unreadable cell from a legitimately empty one.
    """
    clean_val = str(value).replace(",", "").replace("฿", "").replace("$", "").replace("%", "").strip()
    if not clean_val:
        return True
    try:
        float(clean_val)
        return True
    except ValueError:
        return False



def _is_error_value(value: object) -> bool:
    """Return True if ``value`` is a spreadsheet error placeholder such as
    ``#N/A`` or ``#REF!`` (transient while GOOGLEFINANCE/IMPORTRANGE refreshes)."""
    s = str(value).strip().upper()
    return s.startswith("#") or s == "N/A"


def _sum_dr_holdings(holdings: list[DrHolding]) -> tuple[Decimal, int]:
    """Sum DR market values (THB) and count valid DR positions.

    DR values are already THB, so no FX conversion applies here. Blank,
    non-numeric, and negative values are skipped with a warning.
    """
    total = Decimal("0")
    count = 0
    for holding in holdings:
        raw = holding.value_thb.replace(",", "").replace("฿", "").replace("$", "").strip()
        if not raw:
            continue
        try:
            value = Decimal(raw)
        except (InvalidOperation, ValueError):
            logger.warning("Skipping DR holding with unreadable value %r", holding.symbol)
            continue
        if value < 0:
            logger.warning("Skipping DR holding with negative value %r", holding.symbol)
            continue
        total += value
        count += 1
    return total.quantize(TWOPLACES), count


# ── Class-based PortfolioService (domain) ─────────────────────────────────────

class PortfolioService:
    """Builds PortfolioHoldings from raw Portfolio sheet via PortfolioRepository."""

    def __init__(self, repository: PortfolioRepository):
        self.repository = repository

    def get_portfolio(
        self,
        spreadsheet_id: str,
        strict: bool = False,
        fx_rate: Decimal | None = None,
    ) -> ServiceResult[PortfolioResult]:
        """
        Build a combined portfolio from the raw Portfolio sheet (USD) plus the
        DR positions in the 'from Streaming-DR' sheet (THB).

        USD unit prices are converted to THB with ``fx_rate``; DR values are
        already THB and are added as-is. The result separates the two sources so
        the presentation layer can show them as distinct blocks.
        """
        try:
            fetch = self.repository.fetch_portfolio_rows(spreadsheet_id)
            rows = fetch.rows
            items: list[PortfolioItem] = []

            for row in rows:
                try:
                    avg_cost = Decimal(row.avg_cost.replace(",", ""))
                    current_price = Decimal(row.current_price.replace(",", ""))
                    if fx_rate is not None:
                        avg_cost = avg_cost * fx_rate
                        current_price = current_price * fx_rate
                    item = PortfolioItem(
                        symbol=row.symbol,
                        avg_cost=avg_cost,
                        shares=Decimal(row.shares.replace(",", "")),
                        current_price=current_price,
                        currency="USD",
                        source="us",
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

            us_holdings = PortfolioHoldings(items=items)

            dr_fetch = self.repository.fetch_dr_holdings(spreadsheet_id)
            dr_value, dr_positions = _sum_dr_holdings(dr_fetch.holdings)

            return ServiceResult(
                data=PortfolioResult(
                    us_holdings=us_holdings,
                    dr_value=dr_value,
                    dr_positions=dr_positions,
                    dr_skipped=dr_fetch.skipped_count,
                )
            )

        except PortfolioReadError:
            return ServiceResult(error=PORTFOLIO_READ_ERROR)
        except PortfolioParseError:
            return ServiceResult(error=PORTFOLIO_PARSE_ERROR)


# ── Module-level async functions (presentation DTOs) ──────────────────────────

@cached("cash_balance")
async def get_cash_balance(user_info: UserInfo) -> Decimal:
    """Return the 'Cash' entry from AssetAllocation (the source of truth)."""
    allocation = await get_asset_allocation(user_info)
    for entry in allocation.entries:
        if entry.name.strip().lower() == "cash":
            return entry.value
    return Decimal("0")


FX_RATE_CELL = "AssetAllocation!D1"


async def get_fx_rate_thb_per_usd(user_info: UserInfo) -> Decimal:
    """
    Read the live THB/USD rate from AssetAllocation!D1.

    The cell is expected to hold a formula such as
    ``=1*GOOGLEFINANCE("CURRENCY:USDTHB")``; ``get_raw_range`` returns the
    computed (formatted) value, so we parse that numeric string directly.
    """
    try:
        rows = await asyncio.to_thread(
            get_raw_range, user_info.spreadsheet_id, FX_RATE_CELL
        )
    except Exception as e:
        raise SheetsReadError("Failed to read FX rate from AssetAllocation") from e

    raw = ""
    if rows and rows[0] and rows[0][0] is not None:
        raw = str(rows[0][0]).replace(",", "").replace("฿", "").replace("$", "").strip()

    if not raw:
        raise PortfolioParseError("FX rate is missing in AssetAllocation!D1")

    try:
        rate = Decimal(raw)
    except (InvalidOperation, ValueError) as e:
        raise PortfolioParseError("FX rate is not numeric in AssetAllocation!D1") from e

    if rate <= 0:
        raise PortfolioParseError("FX rate must be positive in AssetAllocation!D1")

    return rate


@cached("holdings_index")
async def _fetch_holdings_index(user_info: UserInfo) -> dict[str, HoldingBreakdown]:
    """
    Read the raw Portfolio sheet (Symbol|AvgCost|Shares|CurrentPrice) and build
    an uppercase-symbol -> HoldingBreakdown dict. The sheet is USD-only, so
    market value and cost are converted to THB with the AssetAllocation FX rate;
    weight and profit percent are ratios and therefore unaffected.
    """
    try:
        records = await asyncio.to_thread(get_sheet_records, user_info.spreadsheet_id, "Portfolio")
    except Exception as e:
        raise SheetsReadError("Failed to read Portfolio sheet") from e

    rate = await get_fx_rate_thb_per_usd(user_info)
    rate_f = float(rate)

    parsed: list[tuple[str, float, float, float]] = []
    skipped: list[str] = []

    for row in records:
        symbol = str(row.get("Symbol", "")).strip().upper()
        if not symbol:
            continue

        shares_raw = str(row.get("Shares", "")).strip()
        price_raw = str(row.get("CurrentPrice", "")).strip()

        # Surface silent failures instead of quietly treating bad cells as 0.
        if not _is_numeric(shares_raw):
            skipped.append(f"{symbol}:Shares={shares_raw!r}")
            logger.warning("Holdings: skipping %s, unreadable Shares=%r", symbol, shares_raw)
            continue
        if not _is_numeric(price_raw):
            skipped.append(f"{symbol}:CurrentPrice={price_raw!r}")
            logger.warning("Holdings: skipping %s, unreadable CurrentPrice=%r", symbol, price_raw)
            continue

        shares = _parse_float(shares_raw)
        avg_cost = _parse_float(row.get("AvgCost", "0"))
        current_price = _parse_float(price_raw)

        if shares <= 0:
            skipped.append(f"{symbol}:Shares=0")
            logger.warning("Holdings: skipping %s with zero/empty Shares", symbol)
            continue
        if current_price <= 0:
            skipped.append(f"{symbol}:CurrentPrice=0")
            logger.warning("Holdings: skipping %s with zero/empty CurrentPrice", symbol)
            continue

        market_value_usd = shares * current_price
        cost_usd = shares * avg_cost
        profit_pct = 0.0 if cost_usd <= 0 else ((market_value_usd - cost_usd) / cost_usd) * 100
        parsed.append((symbol, market_value_usd * rate_f, cost_usd * rate_f, profit_pct))

    if skipped:
        logger.warning("Holdings index: skipped %d row(s): %s", len(skipped), "; ".join(skipped))

    total = sum((market_value for _, market_value, _, _ in parsed), 0.0)

    index: dict[str, HoldingBreakdown] = {}
    for symbol, market_value, cost, profit_pct in parsed:
        weight = 0.0 if total == 0 else (market_value / total) * 100
        index[symbol] = HoldingBreakdown(
            symbol=symbol,
            market_value=market_value,
            weight=weight,
            cost=cost,
            profit_pct=profit_pct,
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


@cached("asset_allocation")
async def get_asset_allocation(user_info: UserInfo) -> AssetAllocation:
    """
    Read from the 'AssetAllocation' sheet in ``Type | Value`` format.

    Each row is one asset class with its raw value (e.g. Cash=895541,
    Crypto=212113). Percentages are derived here, so adding a new asset type
    is just adding a row to the sheet.
    """
    try:
        data = await asyncio.to_thread(get_sheet_as_dict, user_info.spreadsheet_id, "AssetAllocation")
    except Exception as e:
        raise SheetsReadError("Failed to read AssetAllocation sheet") from e

    values: list[tuple[str, Decimal]] = []
    for name, raw in data.items():
        name = name.strip()
        if _is_error_value(name):
            # The Type cell itself is an error (e.g. IMPORTRANGE failed to load).
            raise SheetsReadError(DATA_UPDATING)
        if not name:
            continue
        raw_str = str(raw).strip()
        if _is_error_value(raw_str):
            # The Value cell is a transient error (e.g. GOOGLEFINANCE refresh).
            raise SheetsReadError(DATA_UPDATING)
        try:
            value = Decimal(raw_str.replace(",", "").replace("฿", "").replace("$", ""))
        except Exception:
            logger.warning("Skipping invalid allocation entry %s", name)
            continue
        if value < 0:
            logger.warning("Skipping negative allocation entry %s", name)
            continue
        values.append((name, value))

    if not values:
        return AssetAllocation(entries=[])

    total = sum((v for _, v in values), Decimal("0"))
    entries: list[AssetAllocationEntry] = []
    for name, value in values:
        percent = Decimal("0") if total == 0 else ((value / total) * 100).quantize(TWOPLACES)
        entries.append(AssetAllocationEntry(name=name, value=value, percent=percent))

    return AssetAllocation(entries=entries)


@cached("asset_breakdown")
async def get_asset_breakdown(user_info: UserInfo, category: str) -> AssetBreakdown:
    """Drill-down detail for one asset category, with % of each sub-item.

    Reads the configured breakdown range (B=name, C=value) and computes each
    item's share of the category total, sorted by value descending. Parsing
    stops at the first blank row, so the range can stay generous (e.g. A1:C50)
    without tracking the exact row count. Unknown categories return an empty
    breakdown instead of raising.
    """
    canonical = resolve_breakdown_category(category)
    if canonical is None:
        return AssetBreakdown(category=category, items=[])

    config = ASSET_BREAKDOWN_RANGES[canonical]
    # The sheet name must be part of the A1 range: get_raw_range treats a bare
    # range like "A1:C50" as a worksheet *title*, not a cell range, and raises
    # SheetNotFoundError. Combine sheet + range into e.g. "from Sum Wealth!A1:C50".
    a1_range = f"{config['sheet']}!{config['range']}"
    try:
        rows = await asyncio.to_thread(
            get_raw_range, user_info.spreadsheet_id, a1_range
        )
    except Exception as e:
        # Log the real cause (type + message + traceback) before it is wrapped
        # into a generic SheetsReadError and surfaced as the DATA_UPDATING fallback.
        logger.exception(
            "Failed to read asset breakdown (category=%r, range=%r)",
            canonical,
            a1_range,
        )
        raise SheetsReadError("Failed to read asset breakdown") from e

    raw_items: list[tuple[str, float]] = []
    for row in rows:
        if not row or all(not str(cell).strip() for cell in row):
            break  # dynamic range: stop at the first blank row
        name = str(row[1]).strip() if len(row) > 1 else ""
        if not name:
            continue
        raw_value = str(row[2]).strip() if len(row) > 2 else ""
        value = _parse_float(raw_value)
        if value <= 0:
            continue
        raw_items.append((name, value))

    total = sum((value for _, value in raw_items), 0.0)
    items = [
        AssetBreakdownItem(
            name=name,
            value=value,
            percent=0.0 if total == 0 else round((value / total) * 100, 1),
        )
        for name, value in raw_items
    ]
    items.sort(key=lambda item: item.value, reverse=True)
    return AssetBreakdown(category=canonical, items=items)


async def get_dr_pending_flags(user_info: UserInfo) -> int:
    """Read the ⚠️ pending-review counter from 'from Streaming-DR'!O1.

    Returns 0 when the cell is missing, blank, or unreadable so a transient
    read error can never break the summary command.
    """
    try:
        rows = await asyncio.to_thread(
            get_raw_range, user_info.spreadsheet_id, "from Streaming-DR!O1"
        )
    except Exception:
        return 0
    if not rows or not rows[0]:
        return 0
    raw = str(rows[0][0]).strip()
    if not raw or raw.startswith("#"):
        return 0
    try:
        return int(float(raw.replace(",", "")))
    except ValueError:
        return 0


ALLOCATION_TOLERANCE = Decimal("0.5")


def allocation_balance_check(allocation: AssetAllocation) -> tuple[bool, Decimal]:
    """Return (within_tolerance, total_pct). Empty allocation is within tolerance (no warning)."""
    if allocation is None or allocation.is_empty:
        return True, Decimal("0")
    total = allocation.total_percent
    return abs(total - Decimal("100")) <= ALLOCATION_TOLERANCE, total

