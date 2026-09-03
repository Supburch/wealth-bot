"""
test_portfolio_service.py — Unit tests for services/portfolio_service.py

All Sheets I/O is mocked — no real API calls.

Tests:
- get_cash_balance reads the Cash entry from AssetAllocation
- get_all_holdings derives holdings from the raw Portfolio sheet
- get_holding_breakdown uses O(1) dict index (hit / miss / case-insensitive)
- get_top_holdings returns sorted by weight descending
"""
import pytest
from decimal import Decimal
from unittest.mock import patch
from services import cache as cache_module
from models.user import UserInfo


MOCK_ALLOCATION_DICT = {
    "Cash": "฿95,111.27",
    "Retirement Savings": "฿431,511",
    "Stock USA": "฿87,850",
}

MOCK_PORTFOLIO_RECORDS = [
    {"Symbol": "MSFT", "AvgCost": "100", "Shares": "2", "CurrentPrice": "200"},
    {"Symbol": "V",    "AvgCost": "200", "Shares": "1", "CurrentPrice": "100"},
    {"Symbol": "NFLX", "AvgCost": "50",  "Shares": "4", "CurrentPrice": "25"},
]


@pytest.fixture(autouse=True)
async def reset_cache():
    await cache_module.clear_cache()
    yield
    await cache_module.clear_cache()

@pytest.fixture
def mock_user() -> UserInfo:
    return UserInfo(user_id="U1", spreadsheet_id="test_sheet", role="user", enabled=True)


async def test_get_cash_balance(mock_user):
    with patch("services.portfolio_service.get_sheet_as_dict", return_value=MOCK_ALLOCATION_DICT):
        from services.portfolio_service import get_cash_balance
        result = await get_cash_balance(mock_user)

    assert result == Decimal("95111.27")


async def test_get_cash_balance_zero_when_absent(mock_user):
    with patch("services.portfolio_service.get_sheet_as_dict", return_value={"Stock USA": "฿100"}):
        from services.portfolio_service import get_cash_balance
        result = await get_cash_balance(mock_user)

    assert result == Decimal("0")


async def test_get_all_holdings_derives_from_portfolio(mock_user):
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_PORTFOLIO_RECORDS):
        from services.portfolio_service import get_all_holdings
        result = await get_all_holdings(mock_user)

    assert len(result) == 3
    by_symbol = {h.symbol: h for h in result}
    assert set(by_symbol) == {"MSFT", "V", "NFLX"}
    assert by_symbol["MSFT"].market_value == 400.0
    assert by_symbol["MSFT"].cost == 200.0
    assert by_symbol["MSFT"].profit_pct == 100.0
    assert by_symbol["MSFT"].weight == pytest.approx(400 / 600 * 100)


async def test_get_holding_breakdown_hit(mock_user):
    """MSFT lookup should return the correct HoldingBreakdown via O(1) index."""
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_PORTFOLIO_RECORDS):
        from services.portfolio_service import get_holding_breakdown
        result = await get_holding_breakdown(mock_user, "MSFT")

    assert result is not None
    assert result.symbol == "MSFT"
    assert result.profit_pct == 100.0


async def test_get_holding_breakdown_miss(mock_user):
    """Unknown symbol should return None."""
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_PORTFOLIO_RECORDS):
        from services.portfolio_service import get_holding_breakdown
        result = await get_holding_breakdown(mock_user, "ZZZZ")

    assert result is None


async def test_get_holding_breakdown_case_insensitive(mock_user):
    """Lowercase symbol should resolve the same as uppercase."""
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_PORTFOLIO_RECORDS):
        from services.portfolio_service import get_holding_breakdown
        result = await get_holding_breakdown(mock_user, "msft")

    assert result is not None
    assert result.symbol == "MSFT"


async def test_get_top_holdings_sorted(mock_user):
    """get_top_holdings should return holdings sorted by weight descending."""
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_PORTFOLIO_RECORDS):
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

