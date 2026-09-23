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
from unittest.mock import patch, AsyncMock
from services import cache as cache_module
from models.user import UserInfo


def _zero_dr_totals():
    """A DrTotals with all zeros for tests that don't care about DR."""
    from services.portfolio_service import DrTotals
    return DrTotals(Decimal("0"), Decimal("0"), 0, 0)


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


@pytest.fixture(autouse=True)
def _default_fx_rate():
    """Default THB/USD rate = 1 so holdings tests see raw USD-derived numbers."""
    with patch("services.portfolio_service.get_raw_range", return_value=[["1"]]):
        yield


async def test_get_cash_balance(mock_user):
    with patch("services.portfolio_service.get_sheet_as_dict", return_value=MOCK_ALLOCATION_DICT), \
         patch("services.portfolio_service.get_dr_totals", AsyncMock(return_value=_zero_dr_totals())):
        from services.portfolio_service import get_cash_balance
        result = await get_cash_balance(mock_user)

    assert result == Decimal("95111.27")


async def test_get_cash_balance_zero_when_absent(mock_user):
    with patch("services.portfolio_service.get_sheet_as_dict", return_value={"Stock USA": "฿100"}), \
         patch("services.portfolio_service.get_dr_totals", AsyncMock(return_value=_zero_dr_totals())):
        from services.portfolio_service import get_cash_balance
        result = await get_cash_balance(mock_user)

    assert result == Decimal("0")


async def test_get_asset_allocation_raises_on_error_value(mock_user):
    """A transient #N/A in a Value cell surfaces as SheetsReadError(DATA_UPDATING)."""
    from core.exceptions import SheetsReadError
    from core.messages import DATA_UPDATING
    from services.portfolio_service import get_asset_allocation
    with patch("services.portfolio_service.get_sheet_as_dict",
               return_value={"Stock USA": "#N/A", "Cash": "฿95,000"}):
        with pytest.raises(SheetsReadError) as exc:
            await get_asset_allocation(mock_user)
    assert str(exc.value) == DATA_UPDATING


async def test_get_asset_allocation_raises_on_error_type(mock_user):
    """A transient #REF! in the Type column also surfaces as SheetsReadError."""
    from core.exceptions import SheetsReadError
    from core.messages import DATA_UPDATING
    from services.portfolio_service import get_asset_allocation
    with patch("services.portfolio_service.get_sheet_as_dict",
               return_value={"#REF!": "", "Cash": "฿95,000"}):
        with pytest.raises(SheetsReadError) as exc:
            await get_asset_allocation(mock_user)
    assert str(exc.value) == DATA_UPDATING


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


def test_parse_float_handles_sheet_errors():
    from services.portfolio_service import _parse_float
    assert _parse_float("#N/A") == 0.0
    assert _parse_float("#REF!") == 0.0
    assert _parse_float("not-a-number") == 0.0


def test_is_numeric_helper():
    from services.portfolio_service import _is_numeric
    assert _is_numeric("") is True
    assert _is_numeric("123.45") is True
    assert _is_numeric("฿1,234") is True
    assert _is_numeric("#N/A") is False
    assert _is_numeric("not-a-number") is False


def test_is_error_value_helper():
    from services.portfolio_service import _is_error_value
    assert _is_error_value("#N/A") is True
    assert _is_error_value("#REF!") is True
    assert _is_error_value("n/a") is True
    assert _is_error_value("123.45") is False
    assert _is_error_value("") is False
    assert _is_error_value("  ") is False


async def test_get_all_holdings_skips_unreadable_and_zero_rows(mock_user):
    records = [
        {"Symbol": "MSFT", "AvgCost": "100", "Shares": "2", "CurrentPrice": "200"},
        {"Symbol": "BAD", "AvgCost": "10", "Shares": "#N/A", "CurrentPrice": "50"},
        {"Symbol": "SOLD", "AvgCost": "10", "Shares": "0", "CurrentPrice": "50"},
        {"Symbol": "NOPRICE", "AvgCost": "10", "Shares": "1", "CurrentPrice": "#N/A"},
        {"Symbol": "V", "AvgCost": "200", "Shares": "1", "CurrentPrice": "100"},
    ]
    with patch("services.portfolio_service.get_sheet_records", return_value=records):
        from services.portfolio_service import get_all_holdings
        result = await get_all_holdings(mock_user)

    by_symbol = {h.symbol: h for h in result}
    assert set(by_symbol) == {"MSFT", "V"}
    assert by_symbol["MSFT"].market_value == 400.0
    assert by_symbol["V"].market_value == 100.0


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


# ── Currency conversion (USD → THB) ─────────────────────────────────────────────

async def test_get_all_holdings_converts_usd_to_thb(mock_user):
    """Holdings derived from the USD Portfolio sheet are converted to THB."""
    rate = Decimal("32.94")
    with patch("services.portfolio_service.get_sheet_records", return_value=MOCK_PORTFOLIO_RECORDS), \
         patch("services.portfolio_service.get_raw_range", return_value=[[str(rate)]]):
        from services.portfolio_service import get_all_holdings
        result = await get_all_holdings(mock_user)

    by_symbol = {h.symbol: h for h in result}
    assert by_symbol["MSFT"].market_value == pytest.approx(400.0 * float(rate))
    assert by_symbol["MSFT"].cost == pytest.approx(200.0 * float(rate))
    # Ratios are currency-agnostic and must stay identical to the USD case.
    assert by_symbol["MSFT"].profit_pct == 100.0
    assert by_symbol["MSFT"].weight == pytest.approx(400 / 600 * 100)


async def test_get_fx_rate_thb_per_usd_reads_cell(mock_user):
    from services.portfolio_service import get_fx_rate_thb_per_usd
    with patch("services.portfolio_service.get_raw_range", return_value=[["32.9445"]]):
        rate = await get_fx_rate_thb_per_usd(mock_user)
    assert rate == Decimal("32.9445")


async def test_get_fx_rate_thb_per_usd_missing_raises(mock_user):
    from core.exceptions import PortfolioParseError
    from services.portfolio_service import get_fx_rate_thb_per_usd
    with patch("services.portfolio_service.get_raw_range", return_value=[[""]]):
        with pytest.raises(PortfolioParseError):
            await get_fx_rate_thb_per_usd(mock_user)


async def test_get_fx_rate_thb_per_usd_non_numeric_raises(mock_user):
    from core.exceptions import PortfolioParseError
    from services.portfolio_service import get_fx_rate_thb_per_usd
    with patch("services.portfolio_service.get_raw_range", return_value=[["abc"]]):
        with pytest.raises(PortfolioParseError):
            await get_fx_rate_thb_per_usd(mock_user)


def test_get_portfolio_converts_usd_to_thb():
    """Class-based path converts unit prices to THB when fx_rate is provided."""
    from unittest.mock import MagicMock
    from models.portfolio import PortfolioRow
    from repositories.portfolio_repository import DrCostFetchResult
    from services.portfolio_service import PortfolioService

    fetch = MagicMock()
    fetch.rows = [PortfolioRow(symbol="MSFT", avg_cost="100", shares="2", current_price="200")]
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = fetch
    repo.fetch_dr_holdings.return_value = []
    repo.fetch_dr_cost_rows.return_value = DrCostFetchResult(rows=[])
    repo.fetch_dr_cost_rows_section2.return_value = []

    result = PortfolioService(repo).get_portfolio("sheet", fx_rate=Decimal("32.94"))

    assert result.is_success
    item = result.data.us_holdings.items[0]
    assert item.market_value == Decimal("13176.00")
    assert item.total_cost == Decimal("6588.00")
    assert result.data.dr_value == Decimal("0")
    assert result.data.total_value == Decimal("13176.00")


# ── DR aggregation (US + DR combined) ──────────────────────────────────────────

def _portfolio_repo(us_rows, dr_symbols=None, dr_cost_rows=None, dr_section2_rows=None):
    from unittest.mock import MagicMock
    from repositories.portfolio_repository import DrCostFetchResult

    fetch = MagicMock()
    fetch.rows = us_rows
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = fetch
    repo.fetch_dr_holdings.return_value = dr_symbols or []
    repo.fetch_dr_cost_rows.return_value = DrCostFetchResult(rows=dr_cost_rows or [])
    repo.fetch_dr_cost_rows_section2.return_value = dr_section2_rows or []
    return repo


def test_get_portfolio_includes_dr_value_and_profit():
    """A DR with a cost row contributes value and profit to the combined result."""
    from models.portfolio import DrCostRow, PortfolioRow
    from services.portfolio_service import PortfolioService

    repo = _portfolio_repo(
        [PortfolioRow(symbol="MSFT", avg_cost="100", shares="2", current_price="200")],
        dr_symbols=["AAPL80"],
        dr_cost_rows=[DrCostRow(symbol="AAPL80", avg_cost="40", volume="100", current_price="50")],
    )
    result = PortfolioService(repo).get_portfolio("sheet", fx_rate=Decimal("32.94"))

    assert result.is_success
    assert result.data.us_value == Decimal("13176.00")
    assert result.data.dr_value == Decimal("5000.00")   # 50 * 100
    assert result.data.dr_cost == Decimal("4000.00")     # 40 * 100
    assert result.data.dr_profit == Decimal("1000.00")
    assert result.data.dr_roi_percent == Decimal("25.00")
    assert result.data.total_value == Decimal("18176.00")
    assert result.data.dr_skipped == 0
    assert result.data.total_positions == 2


def test_get_portfolio_skips_dr_without_cost_data():
    """A DR with no matching cost row is excluded and surfaced via dr_skipped."""
    from models.portfolio import PortfolioRow
    from services.portfolio_service import PortfolioService

    repo = _portfolio_repo(
        [PortfolioRow(symbol="MSFT", avg_cost="100", shares="2", current_price="200")],
        dr_symbols=["AAPL80"],
        dr_cost_rows=[],
    )
    result = PortfolioService(repo).get_portfolio("sheet", fx_rate=Decimal("32.94"))

    assert result.is_success
    assert result.data.dr_value == Decimal("0")
    assert result.data.dr_cost == Decimal("0")
    assert result.data.dr_skipped == 1
    assert result.data.total_value == Decimal("13176.00")
    assert result.data.total_positions == 1


def test_get_portfolio_dr_symbol_match_is_case_insensitive():
    from models.portfolio import DrCostRow, PortfolioRow
    from services.portfolio_service import PortfolioService

    repo = _portfolio_repo(
        [PortfolioRow(symbol="MSFT", avg_cost="100", shares="2", current_price="200")],
        dr_symbols=["aapl80"],
        dr_cost_rows=[DrCostRow(symbol="AAPL80", avg_cost="40", volume="100", current_price="50")],
    )
    result = PortfolioService(repo).get_portfolio("sheet", fx_rate=Decimal("32.94"))

    assert result.data.dr_skipped == 0
    assert result.data.dr_value == Decimal("5000.00")


def test_get_portfolio_includes_dr_section2_value_and_profit():
    """Section-2 DR rows (size + avg/current price) contribute via implied volume."""
    from models.portfolio import DrSection2Row, PortfolioRow
    from services.portfolio_service import PortfolioService

    repo = _portfolio_repo(
        [PortfolioRow(symbol="MSFT", avg_cost="100", shares="2", current_price="200")],
        dr_symbols=["ASML01"],
        dr_section2_rows=[
            DrSection2Row(symbol="ASML01", size="6054", avg_price="19.43", current_price="45.75"),
        ],
    )
    result = PortfolioService(repo).get_portfolio("sheet", fx_rate=Decimal("32.94"))

    assert result.is_success
    assert result.data.dr_cost == Decimal("6054.00")     # implied volume × avg = size
    assert result.data.dr_value == Decimal("14254.79")   # 6054 × (45.75 / 19.43)
    assert result.data.dr_skipped == 0
    assert result.data.total_positions == 2


def test_get_portfolio_with_no_dr():
    """An empty DR sheet yields dr_value=0 and no skipped rows."""
    from models.portfolio import PortfolioRow
    from services.portfolio_service import PortfolioService

    repo = _portfolio_repo(
        [PortfolioRow(symbol="MSFT", avg_cost="100", shares="2", current_price="200")],
    )
    result = PortfolioService(repo).get_portfolio("sheet", fx_rate=Decimal("32.94"))

    assert result.is_success
    assert result.data.dr_value == Decimal("0")
    assert result.data.dr_cost == Decimal("0")
    assert result.data.dr_skipped == 0
    assert result.data.total_value == Decimal("13176.00")
    assert result.data.total_positions == 1


# ── Asset breakdown (drill-down) ────────────────────────────────────────────────

async def test_get_asset_breakdown_computes_percent_and_sorts(mock_user):
    from services.portfolio_service import get_asset_breakdown
    with patch(
        "services.portfolio_service.get_raw_range",
        return_value=[
            ["", "PVD", "97627"],
            ["", "MT Life", "180,000"],
            ["", "SSO", "171000"],
        ],
    ):
        result = await get_asset_breakdown(mock_user, "Retirement Savings")

    assert result.category == "Retirement Savings"
    assert [i.name for i in result.items] == ["MT Life", "SSO", "PVD"]  # sorted desc
    assert result.total == 448627.0
    percents = {i.name: i.percent for i in result.items}
    assert percents["MT Life"] == 40.1
    assert percents["SSO"] == 38.1
    assert percents["PVD"] == 21.8


async def test_get_asset_breakdown_passes_sheet_name_in_range(mock_user):
    """Regression: the source sheet name must be prepended to the A1 range.

    A bare range like 'A1:C50' is interpreted by get_raw_range as a worksheet
    title (no '!'), which raises SheetNotFoundError and surfaces as the
    DATA_UPDATING fallback. The correct call is 'from Sum Wealth!A1:C50'.
    """
    from services.portfolio_service import get_asset_breakdown
    with patch(
        "services.portfolio_service.get_raw_range",
        return_value=[],
    ) as mock_get:
        await get_asset_breakdown(mock_user, "Retirement Savings")

    mock_get.assert_called_once_with("test_sheet", "from Sum Wealth!A1:C50")


async def test_get_asset_breakdown_unknown_category_returns_empty(mock_user):
    from services.portfolio_service import get_asset_breakdown
    result = await get_asset_breakdown(mock_user, "Nonexistent")
    assert result.is_empty
    assert result.category == "Nonexistent"


async def test_get_asset_breakdown_stops_at_blank_row(mock_user):
    """Parsing stops at the first blank row (generous range like A1:C50)."""
    from services.portfolio_service import get_asset_breakdown
    with patch(
        "services.portfolio_service.get_raw_range",
        return_value=[
            ["", "PVD", "97627"],
            ["", "", ""],            # blank row → stop
            ["", "SSO", "171000"],   # ignored (after blank)
        ],
    ):
        result = await get_asset_breakdown(mock_user, "Retirement Savings")

    assert [i.name for i in result.items] == ["PVD"]
    assert result.total == 97627.0


# ── DR totals (shared helper) ───────────────────────────────────────────────────

def test_compute_dr_totals_merges_sections():
    """The extracted helper merges section-1 and section-2 cost rows."""
    from models.portfolio import DrCostRow, DrSection2Row
    from services.portfolio_service import compute_dr_totals

    totals = compute_dr_totals(
        dr_symbols=["AAPL80", "ASML01", "ORPHAN80"],
        dr_cost_rows=[
            DrCostRow(symbol="AAPL80", avg_cost="40", volume="100", current_price="50"),
        ],
        dr_section2_rows=[
            DrSection2Row(symbol="ASML01", size="6054", avg_price="19.43", current_price="45.75"),
        ],
    )

    assert totals.dr_value == Decimal("19254.79")   # 5000.00 + 14254.79
    assert totals.dr_cost == Decimal("10054.00")     # 4000.00 + 6054.00
    assert totals.dr_positions == 2
    assert totals.dr_skipped == 1                    # ORPHAN80 has no cost row


def test_replace_dr_value_replaces_only():
    """_replace_dr_value swaps the DR entry value without adding a duplicate."""
    from services.portfolio_service import _replace_dr_value

    values = [
        ("Cash", Decimal("100")),
        ("Stock World (DR)", Decimal("0")),
        ("Stock USA", Decimal("50")),
    ]
    out = _replace_dr_value(values, Decimal("37"))

    assert out == [
        ("Cash", Decimal("100")),
        ("Stock World (DR)", Decimal("37")),
        ("Stock USA", Decimal("50")),
    ]


async def test_get_asset_allocation_replaces_stale_dr_value(mock_user):
    """The 'Stock World (DR)' entry value is replaced with the live DR value."""
    from services.portfolio_service import DrTotals, get_asset_allocation

    alloc = {
        "Cash": "฿95,000",
        "Stock World (DR)": "0.00",
        "Stock USA": "฿87,850",
    }
    dr_totals = DrTotals(
        dr_value=Decimal("37891.00"),
        dr_cost=Decimal("22220.00"),
        dr_positions=7,
        dr_skipped=8,
    )
    with patch("services.portfolio_service.get_sheet_as_dict", return_value=alloc), \
         patch("services.portfolio_service.get_dr_totals", AsyncMock(return_value=dr_totals)):
        result = await get_asset_allocation(mock_user)

    by_name = {e.name: e for e in result.entries}
    assert set(by_name) == {"Cash", "Stock World (DR)", "Stock USA"}
    assert by_name["Stock World (DR)"].value == Decimal("37891.00")
    assert result.total == Decimal("220741.00")


async def test_get_asset_allocation_does_not_add_missing_dr_entry(mock_user):
    """When the sheet has no DR row, the live DR value is not appended."""
    from services.portfolio_service import DrTotals, get_asset_allocation

    alloc = {"Cash": "฿95,000", "Stock USA": "฿87,850"}
    dr_totals = DrTotals(
        dr_value=Decimal("37891.00"),
        dr_cost=Decimal("22220.00"),
        dr_positions=7,
        dr_skipped=8,
    )
    with patch("services.portfolio_service.get_sheet_as_dict", return_value=alloc), \
         patch("services.portfolio_service.get_dr_totals", AsyncMock(return_value=dr_totals)):
        result = await get_asset_allocation(mock_user)

    assert [e.name for e in result.entries] == ["Cash", "Stock USA"]


async def test_get_dr_totals_computes_live_skipped(mock_user):
    """get_dr_totals reports the live skipped count, not the stale O1 counter."""
    from unittest.mock import MagicMock
    from models.portfolio import DrCostRow
    from repositories.portfolio_repository import DrCostFetchResult
    from services.portfolio_service import get_dr_totals

    repo = MagicMock()
    repo.fetch_dr_holdings.return_value = ["AAPL80", "ORPHAN80"]
    repo.fetch_dr_cost_rows.return_value = DrCostFetchResult(
        rows=[DrCostRow(symbol="AAPL80", avg_cost="40", volume="100", current_price="50")]
    )
    repo.fetch_dr_cost_rows_section2.return_value = []

    with patch("services.portfolio_service._dr_repository", return_value=repo):
        totals = await get_dr_totals(mock_user)

    assert totals.dr_skipped == 1
    assert totals.dr_value == Decimal("5000.00")


async def test_get_dr_totals_degrades_on_read_error(mock_user):
    """A DR read error degrades to zero totals instead of breaking the reply."""
    from unittest.mock import MagicMock
    from core.exceptions import PortfolioReadError
    from services.portfolio_service import get_dr_totals

    repo = MagicMock()
    repo.fetch_dr_holdings.side_effect = PortfolioReadError("boom")

    with patch("services.portfolio_service._dr_repository", return_value=repo):
        totals = await get_dr_totals(mock_user)

    assert totals.dr_value == Decimal("0")
    assert totals.dr_cost == Decimal("0")
    assert totals.dr_skipped == 0

