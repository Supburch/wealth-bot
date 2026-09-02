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
from models.user import UserInfo


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

@pytest.fixture
def mock_user() -> UserInfo:
    return UserInfo(user_id="U1", spreadsheet_id="test_sheet", role="user", enabled=True)


async def test_get_portfolio_summary(mock_user):
    with patch("services.portfolio_service.get_sheet_as_dict", return_value=MOCK_PORTFOLIO_DICT):
        from services.portfolio_service import get_portfolio_summary
        result = await get_portfolio_summary(mock_user)

    assert result.portfolio_value == 1_000_000.0
    assert result.cost_basis == 800_000.0
    assert result.profit == 200_000.0
    assert result.profit_pct == 25.0
    assert result.cash == 50_000.0


async def test_get_today_summary(mock_user):
    with patch("services.portfolio_service.get_sheet_as_dict", return_value=MOCK_TODAY_DICT):
        from services.portfolio_service import get_today_summary
        result = await get_today_summary(mock_user)

    assert result.portfolio_value == 1_000_000.0
    assert result.today_profit == 5_000.0
    assert result.today_profit_pct == 0.5


async def test_get_all_holdings(mock_user):
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_HOLDINGS_RECORDS):
        from services.portfolio_service import get_all_holdings
        result = await get_all_holdings(mock_user)

    assert len(result) == 3
    symbols = [h.symbol for h in result]
    assert "AAPL" in symbols
    assert "NVDA" in symbols
    assert "BTC" in symbols


async def test_get_holding_breakdown_hit(mock_user):
    """AAPL lookup should return the correct HoldingBreakdown via O(1) index."""
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_HOLDINGS_RECORDS):
        from services.portfolio_service import get_holding_breakdown
        result = await get_holding_breakdown(mock_user, "AAPL")

    assert result is not None
    assert result.symbol == "AAPL"
    assert result.weight == 30.0
    assert result.profit_pct == 20.0


async def test_get_holding_breakdown_miss(mock_user):
    """Unknown symbol should return None."""
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_HOLDINGS_RECORDS):
        from services.portfolio_service import get_holding_breakdown
        result = await get_holding_breakdown(mock_user, "ZZZZ")

    assert result is None


async def test_get_holding_breakdown_case_insensitive(mock_user):
    """Lowercase symbol should resolve the same as uppercase."""
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_HOLDINGS_RECORDS):
        from services.portfolio_service import get_holding_breakdown
        result = await get_holding_breakdown(mock_user, "aapl")

    assert result is not None
    assert result.symbol == "AAPL"


async def test_get_top_holdings_sorted(mock_user):
    """get_top_holdings should return holdings sorted by weight descending."""
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_HOLDINGS_RECORDS):
        from services.portfolio_service import get_top_holdings
        result = await get_top_holdings(mock_user)

    weights = [h.weight for h in result]
    assert weights == sorted(weights, reverse=True), "Holdings should be sorted by weight desc"


def test_parse_float_helper():
    from services.portfolio_service import _parse_float
    assert _parse_float("฿7,450,000") == 7450000.0
    assert _parse_float(" $1,234.56 ") == 1234.56
    assert _parse_float("20.16%") == 20.16
    assert _parse_float("") == 0.0
    assert _parse_float("  ") == 0.0


def test_get_portfolio_read_error_maps_to_message():
    """PortfolioService.get_portfolio maps PortfolioReadError to the user-facing message."""
    from unittest.mock import MagicMock
    from core.exceptions import PortfolioReadError
    from core.messages import PORTFOLIO_READ_ERROR
    from services.portfolio_service import PortfolioService

    repo = MagicMock()
    repo.fetch_portfolio_rows.side_effect = PortfolioReadError("boom")
    result = PortfolioService(repo).get_portfolio("sheet")

    assert result.is_success is False
    assert result.error == PORTFOLIO_READ_ERROR


def test_get_portfolio_unexpected_error_bubbles_up():
    """Unexpected exceptions are not swallowed into ServiceResult (P2.4a)."""
    from unittest.mock import MagicMock
    from services.portfolio_service import PortfolioService

    repo = MagicMock()
    repo.fetch_portfolio_rows.side_effect = KeyError("boom")
    with pytest.raises(KeyError):
        PortfolioService(repo).get_portfolio("sheet")


MOCK_ALLOCATION_DICT = {
    "Equity": "705000",
    "Bonds": "200000",
    "Cash": "95000"
}

async def test_get_wealth_summary_includes_allocation(mock_user):
    from decimal import Decimal
    with patch("services.portfolio_service.get_sheet_as_dict") as mock_dict, \
         patch("services.portfolio_service.get_sheet_records") as mock_records:
        
        def dict_side_effect(sheet_id, range_name):
            if range_name == "PortfolioSummary":
                return MOCK_PORTFOLIO_DICT
            elif range_name == "AssetAllocation":
                return MOCK_ALLOCATION_DICT
            return {}
        mock_dict.side_effect = dict_side_effect
        mock_records.return_value = MOCK_HOLDINGS_RECORDS

        from services.portfolio_service import get_wealth_summary
        result = await get_wealth_summary(mock_user)

    assert result.summary.portfolio_value == 1_000_000.0
    assert len(result.top_holdings) == 3
    assert result.asset_allocation is not None
    assert result.asset_allocation.total == Decimal("1000000.00")
    assert {
        e.name: e.percent for e in result.asset_allocation.entries
    } == {
        "Equity": Decimal("70.50"),
        "Bonds": Decimal("20.00"),
        "Cash": Decimal("9.50"),
    }

async def test_get_wealth_summary_degrades_gracefully_on_allocation_error(mock_user):
    with patch("services.portfolio_service.get_sheet_as_dict") as mock_dict, \
         patch("services.portfolio_service.get_sheet_records") as mock_records:
        
        def dict_side_effect(sheet_id, range_name):
            if range_name == "PortfolioSummary":
                return MOCK_PORTFOLIO_DICT
            elif range_name == "AssetAllocation":
                raise ValueError("Sheet error")
            return {}
        mock_dict.side_effect = dict_side_effect
        mock_records.return_value = MOCK_HOLDINGS_RECORDS

        from services.portfolio_service import get_wealth_summary
        result = await get_wealth_summary(mock_user)

    assert result.summary.portfolio_value == 1_000_000.0
    assert result.asset_allocation is None

async def test_get_wealth_summary_best_worst_multiple_holdings(mock_user):
    with patch("services.portfolio_service.get_sheet_as_dict") as mock_dict, \
         patch("services.portfolio_service.get_sheet_records") as mock_records:
        mock_dict.return_value = MOCK_PORTFOLIO_DICT
        mock_records.return_value = MOCK_HOLDINGS_RECORDS  # 3 holdings: AAPL (20%), NVDA (100%), BTC (25%)
        from services.portfolio_service import get_wealth_summary
        result = await get_wealth_summary(mock_user)
    
    assert result.best_performer == "NVDA"
    assert result.worst_performer == "AAPL"

async def test_get_wealth_summary_best_worst_single_holding(mock_user):
    with patch("services.portfolio_service.get_sheet_as_dict") as mock_dict, \
         patch("services.portfolio_service.get_sheet_records") as mock_records:
        mock_dict.return_value = MOCK_PORTFOLIO_DICT
        mock_records.return_value = [MOCK_HOLDINGS_RECORDS[0]]  # AAPL only
        from services.portfolio_service import get_wealth_summary
        result = await get_wealth_summary(mock_user)
    
    assert result.best_performer == "AAPL"
    assert result.worst_performer is None

async def test_get_wealth_summary_best_worst_zero_holdings(mock_user):
    with patch("services.portfolio_service.get_sheet_as_dict") as mock_dict, \
         patch("services.portfolio_service.get_sheet_records") as mock_records:
        mock_dict.return_value = MOCK_PORTFOLIO_DICT
        mock_records.return_value = []
        from services.portfolio_service import get_wealth_summary
        result = await get_wealth_summary(mock_user)
    
    assert result.best_performer is None
    assert result.worst_performer is None

