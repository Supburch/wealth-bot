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


def test_fetch_dr_holdings_returns_normalized_symbols():
    gateway = FakeGateway([
        # symbol(C index 2) ... L=type(11)
        ["", "", "NVDR", "", "", "", "", "", "", "", "", "DR"],
        ["", "", "AAPL80.BK", "", "", "", "", "", "", "", "", "DR"],
        ["", "", "USA", "", "", "", "", "", "", "", "", "US"],
        [],  # blank row
    ])
    repo = PortfolioRepository(gateway, AppConfig())
    result = repo.fetch_dr_holdings("sheet")

    assert result == ["NVDR", "AAPL80"]


def test_fetch_dr_holdings_empty_sheet():
    repo = PortfolioRepository(FakeGateway([]), AppConfig())
    result = repo.fetch_dr_holdings("sheet")

    assert result == []


def test_fetch_dr_holdings_skips_non_dr_and_blank_rows():
    gateway = FakeGateway([
        ["", "", "", "", "", "", "", "", "", "", "", ""],  # all-blank row
        ["", "", "BOND", "", "", "", "", "", "", "", "", "Bond"],  # non-DR type
    ])
    repo = PortfolioRepository(gateway, AppConfig())
    result = repo.fetch_dr_holdings("sheet")

    assert result == []


def test_fetch_dr_holdings_degrades_when_sheet_not_found():
    class MissingSheetGateway:
        def get_sheet_records(self, spreadsheet_id, range_name):
            raise SheetNotFoundError("from Streaming-DR")

    repo = PortfolioRepository(MissingSheetGateway(), AppConfig())
    result = repo.fetch_dr_holdings("sheet")

    assert result == []


def test_fetch_dr_holdings_still_raises_on_other_read_errors():
    class BrokenGateway:
        def get_sheet_records(self, spreadsheet_id, range_name):
            raise RuntimeError("boom")

    repo = PortfolioRepository(BrokenGateway(), AppConfig())
    with pytest.raises(PortfolioReadError):
        repo.fetch_dr_holdings("sheet")


def test_fetch_dr_cost_rows_returns_valid_rows():
    gateway = FakeGateway([
        # A=avg(0) B=volume(1) D=pct(3) E=symbol(4) F=price(5)
        ["฿10.00", "100", "", "12.5%", "NVDR", "฿12.00"],
        ["20", "50", "", "#N/A", "AAPL80", "18"],  # error % P/L -> skipped
        ["0", "10", "", "5%", "ZERO", "10"],  # non-positive avg cost -> skipped
        ["30", "0", "", "5%", "EMPTYVOL", "10"],  # non-positive volume -> skipped
        ["40", "20", "", "-3%", "AAPL80.BK", "35"],  # valid, normalized symbol
    ])
    repo = PortfolioRepository(gateway, AppConfig())
    result = repo.fetch_dr_cost_rows("sheet")

    assert len(result.rows) == 2
    assert result.rows[0].symbol == "NVDR"
    assert result.rows[0].avg_cost == "฿10.00"
    assert result.rows[0].volume == "100"
    assert result.rows[0].current_price == "฿12.00"
    assert result.rows[1].symbol == "AAPL80"


def test_fetch_dr_cost_rows_degrades_when_sheet_not_found():
    class MissingSheetGateway:
        def get_sheet_records(self, spreadsheet_id, range_name):
            raise SheetNotFoundError("from Streaming-DR")

    repo = PortfolioRepository(MissingSheetGateway(), AppConfig())
    result = repo.fetch_dr_cost_rows("sheet")

    assert result.rows == []


def test_fetch_dr_cost_rows_raises_on_other_read_errors():
    class BrokenGateway:
        def get_sheet_records(self, spreadsheet_id, range_name):
            raise RuntimeError("boom")

    repo = PortfolioRepository(BrokenGateway(), AppConfig())
    with pytest.raises(PortfolioReadError):
        repo.fetch_dr_cost_rows("sheet")


def test_fetch_dr_cost_rows_section2_returns_valid_rows():
    gateway = FakeGateway([
        # C=size(2) E=symbol(4) G=price(6) H=avg(7) M=pct(12)
        ["", "", "฿6,054", "", "ASML01", "", "45.75", "19.43", "", "", "", "", "135.46%"],
        ["", "", "0", "", "ZERO", "", "10", "5", "", "", "", "", "5%"],       # non-positive size -> skipped
        ["", "", "100", "", "ERR", "", "10", "5", "", "", "", "", "#N/A"],    # error % -> skipped
        ["", "", "฿4,060", "", "LOREAL80.BK", "", "1.46", "1.45", "", "", "", "", "0.69%"],
    ])
    repo = PortfolioRepository(gateway, AppConfig())
    result = repo.fetch_dr_cost_rows_section2("sheet")

    assert len(result) == 2
    assert result[0].symbol == "ASML01"
    assert result[0].size == "6054"
    assert result[0].avg_price == "19.43"
    assert result[0].current_price == "45.75"
    assert result[1].symbol == "LOREAL80"
    assert result[1].size == "4060"


def test_fetch_dr_cost_rows_section2_degrades_when_sheet_not_found():
    class MissingSheetGateway:
        def get_sheet_records(self, spreadsheet_id, range_name):
            raise SheetNotFoundError("from Streaming-DR")

    repo = PortfolioRepository(MissingSheetGateway(), AppConfig())
    result = repo.fetch_dr_cost_rows_section2("sheet")

    assert result == []


def test_fetch_dr_cost_rows_section2_raises_on_other_read_errors():
    class BrokenGateway:
        def get_sheet_records(self, spreadsheet_id, range_name):
            raise RuntimeError("boom")

    repo = PortfolioRepository(BrokenGateway(), AppConfig())
    with pytest.raises(PortfolioReadError):
        repo.fetch_dr_cost_rows_section2("sheet")
