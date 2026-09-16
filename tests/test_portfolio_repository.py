"""Unit tests for repositories/portfolio_repository.py short-row handling."""
import pytest

from core.exceptions import PortfolioReadError, SheetNotFoundError
from core.sheet_config import AppConfig
from repositories.portfolio_repository import PortfolioRepository


class FakeGateway:
    def __init__(self, rows):
        self._rows = rows

    def get_sheet_records(self, spreadsheet_id, range_name):
        return self._rows


def test_fetch_portfolio_rows_flags_short_rows():
    gateway = FakeGateway([
        ["AAPL", "150.00", "10", "160.00"],
        ["MSFT"],  # short row: only 1 column
        ["NVDA", "100.00", "5", "120.00"],
    ])
    repo = PortfolioRepository(gateway, AppConfig())
    result = repo.fetch_portfolio_rows("sheet")

    assert len(result.rows) == 2
    assert len(result.short_rows) == 1
    assert result.short_rows[0].row_number == 3  # index 1 + 2 (range starts at A2)
    assert result.short_rows[0].column_count == 1


def test_fetch_portfolio_rows_skips_blank_rows_silently():
    gateway = FakeGateway([
        ["AAPL", "150.00", "10", "160.00"],
        [],  # blank line — not malformed data
        ["NVDA", "100.00", "5", "120.00"],
    ])
    repo = PortfolioRepository(gateway, AppConfig())
    result = repo.fetch_portfolio_rows("sheet")

    assert len(result.rows) == 2
    assert len(result.short_rows) == 0


def test_fetch_dr_holdings_filters_and_skips_flagged():
    gateway = FakeGateway([
        # symbol(A) ... L=type(11)  M=value(12)  N=flag(13)
        ["NVDR", "", "", "", "", "", "", "", "", "", "", "DR", "1000", ""],
        ["AAPL80", "", "", "", "", "", "", "", "", "", "", "DR", "2000", "⚠️ รอตรวจสอบ"],
        ["USA", "", "", "", "", "", "", "", "", "", "", "US", "9999", ""],
        [],  # blank row
    ])
    repo = PortfolioRepository(gateway, AppConfig())
    result = repo.fetch_dr_holdings("sheet")

    assert len(result.holdings) == 1
    assert result.holdings[0].symbol == "NVDR"
    assert result.holdings[0].value_thb == "1000"
    assert result.skipped_count == 1


def test_fetch_dr_holdings_empty_sheet():
    repo = PortfolioRepository(FakeGateway([]), AppConfig())
    result = repo.fetch_dr_holdings("sheet")

    assert result.holdings == []
    assert result.skipped_count == 0


def test_fetch_dr_holdings_skips_non_dr_and_blank_rows():
    gateway = FakeGateway([
        ["", "", "", "", "", "", "", "", "", "", "", "", "", ""],  # all-blank row
        ["BOND", "", "", "", "", "", "", "", "", "", "", "Bond", "123", ""],  # non-DR type
    ])
    repo = PortfolioRepository(gateway, AppConfig())
    result = repo.fetch_dr_holdings("sheet")

    assert result.holdings == []
    assert result.skipped_count == 0


def test_fetch_dr_holdings_degrades_when_sheet_not_found():
    class MissingSheetGateway:
        def get_sheet_records(self, spreadsheet_id, range_name):
            raise SheetNotFoundError("from Streaming-DR")

    repo = PortfolioRepository(MissingSheetGateway(), AppConfig())
    result = repo.fetch_dr_holdings("sheet")

    assert result.holdings == []
    assert result.skipped_count == 0


def test_fetch_dr_holdings_still_raises_on_other_read_errors():
    class BrokenGateway:
        def get_sheet_records(self, spreadsheet_id, range_name):
            raise RuntimeError("boom")

    repo = PortfolioRepository(BrokenGateway(), AppConfig())
    with pytest.raises(PortfolioReadError):
        repo.fetch_dr_holdings("sheet")
