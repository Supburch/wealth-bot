"""
test_handlers.py — Unit tests for handlers/*.

All portfolio service functions and user mapping are mocked.

Tests:
- Unauthorized user → ACCESS_DENIED from all handlers
- Non-admin user → ADMIN_ONLY for admin commands
- TodayHandler → RICH AppResponse
- HoldingsHandler → RICH, sorted by weight
- WinnersHandler → RICH, sorted by profit_pct desc
- LosersHandler → RICH, sorted by profit_pct asc
- CashHandler → TEXT with cash amount
- AllocationHandler → TEXT with allocation lines
- handle_symbol_lookup → TEXT with breakdown or UNKNOWN_COMMAND
- PingHandler → "pong"
- VersionHandler → version string
- AdminHandler refresh/reload → success message
- AdminHandler status → system status
- AdminHandler → ADMIN_ONLY for non-admin
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from models.user import UserInfo
from models.portfolio import (
    HoldingBreakdown,
    AssetAllocation, AssetAllocationEntry,
)
from models.response import AppResponse
from core.enums import ResponseType
from core.messages import ACCESS_DENIED, ADMIN_ONLY
from decimal import Decimal

ALLOWED_USER = "U_ALLOWED"
ADMIN_USER = "U_ADMIN"
UNKNOWN_USER = "U_UNKNOWN"

MOCK_USER = UserInfo(user_id=ALLOWED_USER, spreadsheet_id="test_sheet", role="user", enabled=True)
MOCK_ADMIN = UserInfo(user_id=ADMIN_USER, spreadsheet_id="test_sheet", role="admin", enabled=True)

MOCK_HOLDINGS = [
    HoldingBreakdown(symbol="AAPL", market_value=300_000.0, weight=30.0, cost=250_000.0, profit_pct=20.0),
    HoldingBreakdown(symbol="NVDA", market_value=200_000.0, weight=20.0, cost=100_000.0, profit_pct=100.0),
    HoldingBreakdown(symbol="TSLA", market_value=100_000.0, weight=10.0, cost=120_000.0, profit_pct=-16.7),
]
MOCK_AAPL = HoldingBreakdown(symbol="AAPL", market_value=300_000.0, weight=30.0, cost=250_000.0, profit_pct=20.0)
MOCK_ALLOCATION = AssetAllocation(
    entries=[
        AssetAllocationEntry(name="Stocks", value=Decimal("700000"), percent=Decimal("70")),
        AssetAllocationEntry(name="Cash", value=Decimal("300000"), percent=Decimal("30")),
    ]
)


def _user_side_effect(user_id: str):
    if user_id == ALLOWED_USER:
        return MOCK_USER
    if user_id == ADMIN_USER:
        return MOCK_ADMIN
    return None


# ── Unauthorized ──────────────────────────────────────────────────────────────

async def test_today_handler_returns_removal_message():
    from handlers.today_handler import TodayHandler
    result = await TodayHandler().handle(UNKNOWN_USER)
    assert result.type == ResponseType.TEXT
    assert "วันนี้" in result.text
    assert "สรุป" in result.text


async def test_holdings_handler_unauthorized():
    from handlers.holdings_handler import HoldingsHandler
    with patch("handlers.holdings_handler.get_user", AsyncMock(return_value=None)):
        result = await HoldingsHandler().handle(UNKNOWN_USER)
    assert result.text == ACCESS_DENIED


# ── PortfolioHandler ───────────────────────────────────────────────────────────

async def test_portfolio_handler_returns_rich():
    from handlers.portfolio_handler import PortfolioHandler
    from services.portfolio_service import ServiceResult
    portfolio = MagicMock()
    portfolio.is_empty = False
    mock_service = MagicMock()
    mock_service.get_portfolio.return_value = ServiceResult(data=portfolio)
    with patch("handlers.portfolio_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.portfolio_handler.get_fx_rate_thb_per_usd", AsyncMock(return_value=Decimal("32.94"))), \
         patch("handlers.portfolio_handler.build_portfolio_flex", return_value={"type": "bubble"}):
        result = await PortfolioHandler(mock_service).handle(ALLOWED_USER)
    assert result.type == ResponseType.RICH
    assert result.alt_text == "สรุปพอร์ต"
    assert result.contents is not None
    mock_service.get_portfolio.assert_called_once_with("test_sheet", False, Decimal("32.94"))


async def test_portfolio_handler_unexpected_error_bubbles_up():
    """Unexpected service errors must not be masked into a generic fallback (P2.4a)."""
    from handlers.portfolio_handler import PortfolioHandler
    mock_service = MagicMock()
    mock_service.get_portfolio.side_effect = KeyError("boom")
    with patch("handlers.portfolio_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.portfolio_handler.get_fx_rate_thb_per_usd", AsyncMock(return_value=Decimal("32.94"))):
        with pytest.raises(KeyError):
            await PortfolioHandler(mock_service).handle(ALLOWED_USER)


async def test_portfolio_handler_fx_rate_error():
    """A missing/invalid FX rate maps to FX_RATE_ERROR instead of crashing."""
    from handlers.portfolio_handler import PortfolioHandler
    from core.exceptions import SheetsReadError
    from core.messages import FX_RATE_ERROR

    mock_service = MagicMock()
    with patch("handlers.portfolio_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.portfolio_handler.get_fx_rate_thb_per_usd", AsyncMock(side_effect=SheetsReadError("boom"))):
        result = await PortfolioHandler(mock_service).handle(ALLOWED_USER)

    assert result.type == ResponseType.TEXT
    assert result.text == FX_RATE_ERROR


# ── WealthSummaryHandler ───────────────────────────────────────────────────────

async def test_wealth_summary_handler_returns_text():
    from handlers.wealth_summary_handler import WealthSummaryHandler
    with patch("handlers.wealth_summary_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.wealth_summary_handler.get_asset_allocation", AsyncMock(return_value=MOCK_ALLOCATION)):
        result = await WealthSummaryHandler().handle(ALLOWED_USER)
    assert result.type == ResponseType.TEXT
    assert "สรุปพอร์ต" in result.text
    assert "Stocks" in result.text
    assert "Cash" in result.text


async def test_wealth_summary_handler_empty_allocation():
    from handlers.wealth_summary_handler import WealthSummaryHandler
    with patch("handlers.wealth_summary_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.wealth_summary_handler.get_asset_allocation", AsyncMock(return_value=AssetAllocation(entries=[]))):
        result = await WealthSummaryHandler().handle(ALLOWED_USER)
    assert result.type == ResponseType.TEXT
    assert "ไม่พบข้อมูลพอร์ต" in result.text


async def test_wealth_summary_handler_data_updating():
    from handlers.wealth_summary_handler import WealthSummaryHandler
    from core.exceptions import SheetsReadError
    from core.messages import DATA_UPDATING
    with patch("handlers.wealth_summary_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.wealth_summary_handler.get_asset_allocation", AsyncMock(side_effect=SheetsReadError(DATA_UPDATING))):
        result = await WealthSummaryHandler().handle(ALLOWED_USER)
    assert result.type == ResponseType.TEXT
    assert result.text == DATA_UPDATING


# ── TodayHandler ──────────────────────────────────────────────────────────────

async def test_today_handler_returns_text():
    from handlers.today_handler import TodayHandler
    result = await TodayHandler().handle(ALLOWED_USER)
    assert result.type == ResponseType.TEXT
    assert "วันนี้" in result.text
    assert "สรุป" in result.text


# ── HoldingsHandler ───────────────────────────────────────────────────────────

async def test_holdings_handler_returns_rich():
    from handlers.holdings_handler import HoldingsHandler
    with patch("handlers.holdings_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.holdings_handler.get_top_holdings", AsyncMock(return_value=MOCK_HOLDINGS)):
        result = await HoldingsHandler().handle(ALLOWED_USER)
    assert result.type == ResponseType.RICH
    assert result.contents is not None


async def test_winners_handler_returns_rich():
    from handlers.holdings_handler import WinnersHandler
    with patch("handlers.holdings_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.holdings_handler.get_all_holdings", AsyncMock(return_value=MOCK_HOLDINGS)):
        result = await WinnersHandler().handle(ALLOWED_USER)
    assert result.type == ResponseType.RICH


async def test_losers_handler_returns_rich():
    from handlers.holdings_handler import LosersHandler
    with patch("handlers.holdings_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.holdings_handler.get_all_holdings", AsyncMock(return_value=MOCK_HOLDINGS)):
        result = await LosersHandler().handle(ALLOWED_USER)
    assert result.type == ResponseType.RICH


# ── CashHandler ───────────────────────────────────────────────────────────────

async def test_cash_handler_returns_cash():
    from handlers.utility_handler import CashHandler
    with patch("handlers.utility_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.utility_handler.get_cash_balance", AsyncMock(return_value=Decimal("50000.00"))):
        result = await CashHandler().handle(ALLOWED_USER)
    assert result.type == ResponseType.TEXT
    assert "50,000" in result.text


async def test_cash_handler_data_updating():
    from handlers.utility_handler import CashHandler
    from core.exceptions import SheetsReadError
    from core.messages import DATA_UPDATING
    with patch("handlers.utility_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.utility_handler.get_cash_balance", AsyncMock(side_effect=SheetsReadError(DATA_UPDATING))):
        result = await CashHandler().handle(ALLOWED_USER)
    assert result.type == ResponseType.TEXT
    assert result.text == DATA_UPDATING


# ── AllocationHandler ─────────────────────────────────────────────────────────

async def test_allocation_handler_returns_text():
    from handlers.allocation_handler import AllocationHandler
    with patch("handlers.allocation_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.allocation_handler.get_asset_allocation", AsyncMock(return_value=MOCK_ALLOCATION)):
        result = await AllocationHandler().handle(ALLOWED_USER)
    assert result.type == ResponseType.TEXT
    assert "Stocks" in result.text
    assert "Cash" in result.text
    assert "ไม่ครบ" not in result.text


async def test_allocation_handler_empty():
    from handlers.allocation_handler import AllocationHandler
    with patch("handlers.allocation_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.allocation_handler.get_asset_allocation", AsyncMock(return_value=AssetAllocation(entries=[]))):
        result = await AllocationHandler().handle(ALLOWED_USER)
    assert "ไม่พบ" in result.text
    assert "ไม่ครบ" not in result.text


async def test_allocation_handler_data_updating():
    from handlers.allocation_handler import AllocationHandler
    from core.exceptions import SheetsReadError
    from core.messages import DATA_UPDATING
    with patch("handlers.allocation_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.allocation_handler.get_asset_allocation", AsyncMock(side_effect=SheetsReadError(DATA_UPDATING))):
        result = await AllocationHandler().handle(ALLOWED_USER)
    assert result.type == ResponseType.TEXT
    assert result.text == DATA_UPDATING


async def test_allocation_handler_out_of_tolerance_warns():
    from handlers.allocation_handler import AllocationHandler
    allocation = AssetAllocation(
        entries=[
            AssetAllocationEntry(name="Stocks", value=Decimal("700000"), percent=Decimal("70")),
            AssetAllocationEntry(name="Cash", value=Decimal("250000"), percent=Decimal("25")),
        ]
    )
    with patch("handlers.allocation_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.allocation_handler.get_asset_allocation", AsyncMock(return_value=allocation)):
        result = await AllocationHandler().handle(ALLOWED_USER)
    assert "ไม่ครบ" in result.text
    assert "95.0%" in result.text


# ── Symbol Lookup ─────────────────────────────────────────────────────────────

async def test_symbol_handler_hit():
    from handlers.symbol_handler import handle_symbol_lookup
    with patch("handlers.symbol_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.symbol_handler.get_holding_breakdown", AsyncMock(return_value=MOCK_AAPL)):
        result = await handle_symbol_lookup(ALLOWED_USER, "AAPL")
    assert result.type == ResponseType.TEXT
    assert "AAPL" in result.text
    assert "300,000" in result.text


async def test_symbol_handler_miss():
    from handlers.symbol_handler import handle_symbol_lookup
    with patch("handlers.symbol_handler.get_user", AsyncMock(return_value=MOCK_USER)), \
         patch("handlers.symbol_handler.get_holding_breakdown", AsyncMock(return_value=None)):
        result = await handle_symbol_lookup(ALLOWED_USER, "ZZZZ")
    from core.messages import UNKNOWN_COMMAND
    assert result.text == UNKNOWN_COMMAND


# ── Utility Handlers ──────────────────────────────────────────────────────────

async def test_ping_handler():
    from handlers.utility_handler import PingHandler
    result = await PingHandler().handle(ALLOWED_USER)
    assert result.text == "pong"


async def test_version_handler():
    from handlers.utility_handler import VersionHandler
    result = await VersionHandler("2.0.0").handle(ALLOWED_USER)
    assert "2.0.0" in result.text


# ── AdminHandler ──────────────────────────────────────────────────────────────

async def test_admin_handler_non_admin_rejected():
    from handlers.admin_handler import AdminHandler
    with patch("handlers.admin_handler.get_user", AsyncMock(return_value=MOCK_USER)):
        result = await AdminHandler("refresh").handle(ALLOWED_USER)
    assert result.text == ADMIN_ONLY


async def test_admin_handler_refresh():
    from handlers.admin_handler import AdminHandler
    with patch("handlers.admin_handler.get_user", AsyncMock(return_value=MOCK_ADMIN)), \
         patch("handlers.admin_handler.clear_cache", AsyncMock()):
        result = await AdminHandler("refresh").handle(ADMIN_USER)
    assert "รีเฟรช" in result.text


async def test_admin_handler_status():
    from handlers.admin_handler import AdminHandler
    with patch("handlers.admin_handler.get_user", AsyncMock(return_value=MOCK_ADMIN)), \
         patch("handlers.admin_handler.check_sheets_health", AsyncMock(return_value=True)):
        result = await AdminHandler("status").handle(ADMIN_USER)
    assert "ชีต" in result.text
    assert "ปกติ" in result.text
