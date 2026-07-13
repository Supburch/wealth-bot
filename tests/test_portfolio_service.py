"""
test_portfolio_service.py — Unit tests for services/portfolio_service.py

All Sheets I/O is mocked — no real API calls.

Tests:
- get_portfolio_summary parses Sheets dict correctly
- get_today_summary parses Sheets dict correctly
- get_all_holdings parses records correctly
- get_holding_breakdown uses O(1) dict index (hit / miss / case-insensitive)
- get_top_holdings returns sorted by weight descending
"""
import pytest
from unittest.mock import patch
from services import cache as cache_module


MOCK_PORTFOLIO_DICT = {
    "PortfolioValue": "1000000",
    "CostBasis": "800000",
    "Profit": "200000",
    "ProfitPct": "25.0",
    "Cash": "50000",
}

MOCK_TODAY_DICT = {
    "PortfolioValue": "1000000",
    "TodayProfit": "5000",
    "TodayProfitPct": "0.5",
}

MOCK_HOLDINGS_RECORDS = [
    {"Symbol": "AAPL", "MarketValue": "300000", "Weight": "30.0", "Cost": "250000", "ProfitPct": "20.0"},
    {"Symbol": "NVDA", "MarketValue": "200000", "Weight": "20.0", "Cost": "100000", "ProfitPct": "100.0"},
    {"Symbol": "BTC",  "MarketValue": "100000", "Weight": "10.0", "Cost": "80000",  "ProfitPct": "25.0"},
]


@pytest.fixture(autouse=True)
async def reset_cache():
    await cache_module.clear_cache()
    yield
    await cache_module.clear_cache()


async def test_get_portfolio_summary():
    with patch("services.portfolio_service.get_sheet_as_dict", return_value=MOCK_PORTFOLIO_DICT):
        from services.portfolio_service import get_portfolio_summary
        result = await get_portfolio_summary()

    assert result.portfolio_value == 1_000_000.0
    assert result.cost_basis == 800_000.0
    assert result.profit == 200_000.0
    assert result.profit_pct == 25.0
    assert result.cash == 50_000.0


async def test_get_today_summary():
    with patch("services.portfolio_service.get_sheet_as_dict", return_value=MOCK_TODAY_DICT):
        from services.portfolio_service import get_today_summary
        result = await get_today_summary()

    assert result.portfolio_value == 1_000_000.0
    assert result.today_profit == 5_000.0
    assert result.today_profit_pct == 0.5


async def test_get_all_holdings():
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_HOLDINGS_RECORDS):
        from services.portfolio_service import get_all_holdings
        result = await get_all_holdings()

    assert len(result) == 3
    symbols = [h.symbol for h in result]
    assert "AAPL" in symbols
    assert "NVDA" in symbols
    assert "BTC" in symbols


async def test_get_holding_breakdown_hit():
    """AAPL lookup should return the correct HoldingBreakdown via O(1) index."""
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_HOLDINGS_RECORDS):
        from services.portfolio_service import get_holding_breakdown
        result = await get_holding_breakdown("AAPL")

    assert result is not None
    assert result.symbol == "AAPL"
    assert result.weight == 30.0
    assert result.profit_pct == 20.0


async def test_get_holding_breakdown_miss():
    """Unknown symbol should return None."""
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_HOLDINGS_RECORDS):
        from services.portfolio_service import get_holding_breakdown
        result = await get_holding_breakdown("ZZZZ")

    assert result is None


async def test_get_holding_breakdown_case_insensitive():
    """Lowercase symbol should resolve the same as uppercase."""
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_HOLDINGS_RECORDS):
        from services.portfolio_service import get_holding_breakdown
        result = await get_holding_breakdown("aapl")

    assert result is not None
    assert result.symbol == "AAPL"


async def test_get_top_holdings_sorted():
    """get_top_holdings should return holdings sorted by weight descending."""
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_HOLDINGS_RECORDS):
        from services.portfolio_service import get_top_holdings
        result = await get_top_holdings()

    weights = [h.weight for h in result]
    assert weights == sorted(weights, reverse=True), "Holdings should be sorted by weight desc"
