"""
test_line_commands.py — Unit tests for services/line_service.py

All portfolio service functions and config are mocked — no real API calls.

Tests:
- Unauthorized user → rejected immediately
- พอร์ต → portfolio value/profit format
- สรุป → top holdings and profit pct
- วันนี้ → today profit display
- ถืออะไร → holdings list
- AAPL → breakdown for known symbol
- ZZZZ → fallback "คำสั่งไม่ถูกต้อง"
- aapl → case-insensitive symbol match
"""
import importlib
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from models.portfolio import (
    PortfolioSummary, TodaySummary, HoldingBreakdown, WealthSummary
)
from models.user import UserInfo

ALLOWED_USER = "U_ALLOWED_001"
UNKNOWN_USER = "U_UNKNOWN_999"

MOCK_PORTFOLIO = PortfolioSummary(
    portfolio_value=1_000_000.0,
    cost_basis=800_000.0,
    profit=200_000.0,
    profit_pct=25.0,
    cash=50_000.0,
)

MOCK_TODAY = TodaySummary(
    portfolio_value=1_000_000.0,
    today_profit=5_000.0,
    today_profit_pct=0.5,
)

MOCK_HOLDINGS = [
    HoldingBreakdown(symbol="AAPL", market_value=300_000.0, weight=30.0, cost=250_000.0, profit_pct=20.0),
    HoldingBreakdown(symbol="NVDA", market_value=200_000.0, weight=20.0, cost=100_000.0, profit_pct=100.0),
]

MOCK_WEALTH = WealthSummary(summary=MOCK_PORTFOLIO, top_holdings=MOCK_HOLDINGS)
MOCK_AAPL = HoldingBreakdown(symbol="AAPL", market_value=300_000.0, weight=30.0, cost=250_000.0, profit_pct=20.0)


def _mock_get_user(user_id: str):
    if user_id == ALLOWED_USER:
        return UserInfo(user_id=user_id, spreadsheet_id="test_sheet", role="user", enabled=True)
    return None

@pytest.fixture(autouse=True)
def patch_get_user():
    with patch("services.line_service.get_user", AsyncMock(side_effect=_mock_get_user)):
        yield


async def _call(command: str, user_id: str = ALLOWED_USER) -> str:
    import services.line_service as ls
    return await ls.handle_user_command(user_id, command)


# ── Security ──────────────────────────────────────────────────────────────────

async def test_unauthorized_user():
    reply = await _call("พอร์ต", user_id=UNKNOWN_USER)
    assert reply == "Unauthorized"


# ── พอร์ต ─────────────────────────────────────────────────────────────────────

async def test_port_command():
    with patch("services.line_service.get_portfolio_summary", AsyncMock(return_value=MOCK_PORTFOLIO)):
        reply = await _call("พอร์ต")

    assert "1,000,000" in reply
    assert "800,000" in reply
    assert "200,000" in reply
    assert "25" in reply  # profit_pct


# ── สรุป ──────────────────────────────────────────────────────────────────────

async def test_saroop_command():
    with patch("services.line_service.get_wealth_summary", AsyncMock(return_value=MOCK_WEALTH)):
        reply = await _call("สรุป")

    assert "25" in reply  # profit_pct
    assert "AAPL" in reply or "NVDA" in reply  # top holdings shown


# ── วันนี้ ─────────────────────────────────────────────────────────────────────

async def test_wannee_command():
    with patch("services.line_service.get_today_summary", AsyncMock(return_value=MOCK_TODAY)):
        reply = await _call("วันนี้")

    assert "5,000" in reply
    assert "0.5" in reply


# ── ถืออะไร ───────────────────────────────────────────────────────────────────

async def test_thuarai_command():
    with patch("services.line_service.get_top_holdings", AsyncMock(return_value=MOCK_HOLDINGS)):
        reply = await _call("ถืออะไร")

    assert "AAPL" in reply
    assert "30" in reply  # weight


# ── Symbol Lookup ─────────────────────────────────────────────────────────────

async def test_symbol_lookup_hit():
    with patch("services.line_service.get_holding_breakdown", AsyncMock(return_value=MOCK_AAPL)):
        reply = await _call("AAPL")

    assert "AAPL" in reply
    assert "300,000" in reply
    assert "20" in reply  # profit_pct


async def test_symbol_lookup_miss():
    with patch("services.line_service.get_holding_breakdown", AsyncMock(return_value=None)):
        reply = await _call("ZZZZ")

    assert "help" in reply.lower() or "คำสั่งไม่ถูกต้อง" in reply


async def test_symbol_lookup_case_insensitive():
    """Lowercase 'aapl' should resolve the same as 'AAPL'."""
    with patch("services.line_service.get_holding_breakdown", AsyncMock(return_value=MOCK_AAPL)) as mock_fn:
        reply = await _call("aapl")

    assert "AAPL" in reply
    mock_fn.assert_called_once()
