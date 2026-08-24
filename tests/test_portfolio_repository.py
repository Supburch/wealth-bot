"""Unit tests for repositories/portfolio_repository.py short-row handling."""
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
