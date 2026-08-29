import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal

from models.portfolio import PortfolioRow
from core.exceptions import PortfolioReadError
from services.validation_service import ValidationService
from handlers.validate_handler import ValidateHandler
from models.validation import ValidationIssue, ValidationResult, ValidationSummary
from models.response import AppResponse
from core.enums import ResponseType
from core.messages import ACCESS_DENIED
from models.user import UserInfo
from repositories.portfolio_repository import PortfolioFetchResult, ShortRow
from repositories.validation_result_repository import GoogleSheetResultRepository
from services.writeback_service import WriteBackService


MOCK_USER = UserInfo(user_id="U_ALLOWED", spreadsheet_id="test_sheet", role="user", enabled=True)

# ── ValidationService Tests ──────────────────────────────────────────────────

def test_validation_service_success():
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol="AAPL", avg_cost="150.00", shares="10", current_price="160.00"),
            PortfolioRow(symbol="MSFT", avg_cost="250.00", shares="5", current_price="280.00"),
        ],
        short_rows=[],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is True
    assert summary.total_rows == 2
    assert summary.valid_rows == 2
    assert summary.invalid_rows == 0
    assert len(summary.issues) == 0


def test_validation_service_with_invalid_numbers():
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol="AAPL", avg_cost="150.00", shares="10", current_price="160.00"),
            # Invalid shares
            PortfolioRow(symbol="MSFT", avg_cost="250.00", shares="N/A", current_price="280.00"),
        ],
        short_rows=[],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is False
    assert summary.total_rows == 2
    assert summary.valid_rows == 1
    assert summary.invalid_rows == 1
    assert len(summary.issues) == 1
    assert summary.issues[0].row_index == 3 # 0-indexed data + 2 for header = row 3
    assert summary.issues[0].symbol == "MSFT"
    assert "Invalid number format" in summary.issues[0].error_message


def test_validation_service_with_negative_values():
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol="AAPL", avg_cost="-150.00", shares="10", current_price="160.00"),
            PortfolioRow(symbol="MSFT", avg_cost="250.00", shares="-5", current_price="280.00"),
        ],
        short_rows=[],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is False
    assert summary.valid_rows == 0
    assert summary.invalid_rows == 2
    assert len(summary.issues) == 2
    assert "Prices cannot be negative" in summary.issues[0].error_message
    assert "Shares cannot be negative" in summary.issues[1].error_message


def test_validation_service_short_row_produces_issue():
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol="AAPL", avg_cost="150.00", shares="10", current_price="160.00"),
        ],
        short_rows=[ShortRow(row_number=5, column_count=2)],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is False
    assert summary.total_rows == 2
    assert summary.valid_rows == 1
    assert summary.invalid_rows == 1
    assert len(summary.issues) == 1
    assert summary.issues[0].row_index == 5
    assert summary.issues[0].symbol == "UNKNOWN"
    assert "has only 2 columns, expected 4" in summary.issues[0].error_message


def test_validation_service_read_error():
    repo = MagicMock()
    repo.fetch_portfolio_rows.side_effect = PortfolioReadError("Mock Read Error")
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is False
    assert summary.invalid_rows == 1
    assert summary.issues[0].symbol == "SYSTEM"
    assert "Failed to read Google Sheet" in summary.issues[0].error_message


def test_validation_service_unexpected_error_bubbles_up():
    """Unexpected exceptions must not be masked as a SYSTEM ValidationIssue (P2.4a)."""
    repo = MagicMock()
    repo.fetch_portfolio_rows.side_effect = KeyError("boom")
    service = ValidationService(repo)
    with pytest.raises(KeyError):
        service.validate_portfolio("dummy_id")


def test_validation_service_duplicate_symbols_flagged():
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol="AAPL", avg_cost="150.00", shares="10", current_price="160.00"),
            PortfolioRow(symbol="AAPL", avg_cost="150.00", shares="5", current_price="160.00"),
        ],
        short_rows=[],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is False
    assert summary.total_rows == 2
    assert summary.valid_rows == 2
    assert summary.invalid_rows == 1
    assert len(summary.issues) == 1
    assert summary.issues[0].symbol == "AAPL"
    assert summary.issues[0].error_message == "Duplicate symbol 'AAPL' at rows 2, 3"


def test_validation_service_duplicate_with_parse_error_still_flagged():
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol="AAPL", avg_cost="150.00", shares="10", current_price="160.00"),
            PortfolioRow(symbol="AAPL", avg_cost="150.00", shares="N/A", current_price="160.00"),
        ],
        short_rows=[],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is False
    assert summary.total_rows == 2
    assert summary.valid_rows == 1
    assert summary.invalid_rows == 2

    # The bad-shares row still gets its own parse error.
    assert any(
        i.row_index == 3 and "Invalid number format for shares" in i.error_message
        for i in summary.issues
    )
    # Both rows share the same symbol, so a duplicate is also flagged.
    assert any(
        i.error_message == "Duplicate symbol 'AAPL' at rows 2, 3"
        for i in summary.issues
    )


def test_validation_service_two_empty_symbols_not_duplicates():
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol="", avg_cost="150.00", shares="10", current_price="160.00"),
            PortfolioRow(symbol="   ", avg_cost="250.00", shares="5", current_price="280.00"),
        ],
        short_rows=[],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is False
    assert summary.valid_rows == 0
    assert summary.invalid_rows == 2
    assert len(summary.issues) == 2
    assert all(i.error_message == "Symbol is empty" for i in summary.issues)
    assert not any("Duplicate" in i.error_message for i in summary.issues)


def test_validation_service_unique_symbols_no_duplicate_issue():
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol="AAPL", avg_cost="150.00", shares="10", current_price="160.00"),
            PortfolioRow(symbol="MSFT", avg_cost="250.00", shares="5", current_price="280.00"),
        ],
        short_rows=[],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is True
    assert summary.valid_rows == 2
    assert summary.invalid_rows == 0
    assert len(summary.issues) == 0


def test_validation_service_zero_shares_flagged():
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol="AAPL", avg_cost="150.00", shares="0", current_price="160.00"),
        ],
        short_rows=[],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is False
    assert summary.invalid_rows == 1
    assert summary.issues[0].error_message == "Shares cannot be zero"


def test_validation_service_zero_price_flagged():
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol="MSFT", avg_cost="250.00", shares="5", current_price="0"),
        ],
        short_rows=[],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is False
    assert summary.invalid_rows == 1
    assert summary.issues[0].error_message == "Prices cannot be zero"


def test_validation_service_blank_symbol_flagged():
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol="", avg_cost="150.00", shares="10", current_price="160.00"),
        ],
        short_rows=[],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is False
    assert summary.invalid_rows == 1
    assert summary.issues[0].symbol == "UNKNOWN"
    assert summary.issues[0].error_message == "Symbol is empty"


def test_validation_service_blank_numeric_field_flagged():
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol="MSFT", avg_cost="", shares="5", current_price="280.00"),
        ],
        short_rows=[],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is False
    assert summary.invalid_rows == 1
    assert summary.issues[0].error_message == "Average cost is empty"


def test_validation_service_wrong_type_field_flagged():
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol="MSFT", avg_cost="250.00", shares="N/A", current_price="280.00"),
        ],
        short_rows=[],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is False
    assert summary.invalid_rows == 1
    assert summary.issues[0].error_message == "Invalid number format for shares"


def test_validation_service_valid_symbol_formats_pass():
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol="AAPL", avg_cost="150.00", shares="10", current_price="160.00"),
            PortfolioRow(symbol="BTC", avg_cost="250.00", shares="5", current_price="280.00"),
            PortfolioRow(symbol="X", avg_cost="1.00", shares="1", current_price="2.00"),
            PortfolioRow(symbol="PTT.BK", avg_cost="30.00", shares="100", current_price="35.00"),
            PortfolioRow(symbol="BRK.B", avg_cost="400.00", shares="2", current_price="410.00"),
            PortfolioRow(symbol="ADVANC.BK", avg_cost="200.00", shares="10", current_price="210.00"),
        ],
        short_rows=[],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is True
    assert summary.valid_rows == 6
    assert summary.invalid_rows == 0
    assert len(summary.issues) == 0


@pytest.mark.parametrize(
    "bad_symbol",
    ["brk.b", "AAPL123", "AAPL US", "12345", "AAPL.", "AAPL.BKKK"],
)
def test_validation_service_unusual_symbol_format_flagged(bad_symbol):
    repo = MagicMock()
    repo.fetch_portfolio_rows.return_value = PortfolioFetchResult(
        rows=[
            PortfolioRow(symbol=bad_symbol, avg_cost="150.00", shares="10", current_price="160.00"),
        ],
        short_rows=[],
    )
    service = ValidationService(repo)
    summary = service.validate_portfolio("dummy_id")

    assert summary.is_valid is False
    assert summary.invalid_rows == 1
    assert len(summary.issues) == 1
    assert summary.issues[0].symbol == bad_symbol
    assert "Unusual symbol format" in summary.issues[0].error_message


def test_validation_result_to_rows_for_valid_summary():
    summary = ValidationSummary(total_rows=2, valid_rows=2, invalid_rows=0, issues=[])
    result = ValidationResult(spreadsheet_id="sheet_1", summary=summary, run_id="run_1")

    rows = result.to_rows()

    assert rows[0] == result.header
    assert rows[1][0] == "run_1"
    assert rows[1][2] == "valid"
    assert rows[1][3:6] == [2, 2, 0]
    assert rows[1][6:] == ["", "", ""]


def test_validation_result_to_rows_for_issues():
    summary = ValidationSummary(
        total_rows=2,
        valid_rows=1,
        invalid_rows=1,
        issues=[
            ValidationIssue(row_index=3, symbol="MSFT", error_message="Invalid shares")
        ],
    )
    result = ValidationResult(spreadsheet_id="sheet_1", summary=summary, run_id="run_2")

    rows = result.to_rows()

    assert rows[1][2] == "invalid"
    assert rows[1][6:] == [3, "MSFT", "Invalid shares"]


def test_validation_result_preserves_system_row_zero():
    summary = ValidationSummary(
        total_rows=0,
        valid_rows=0,
        invalid_rows=1,
        issues=[ValidationIssue(row_index=0, symbol="SYSTEM", error_message="Read failed")],
    )
    result = ValidationResult(spreadsheet_id="sheet_1", summary=summary)

    rows = result.to_rows()

    assert rows[1][6:] == [0, "SYSTEM", "Read failed"]


def test_google_sheet_result_repository_uses_configured_sheet():
    gateway = MagicMock()
    config = MagicMock(validation_result_sheet="ValidationResult")
    repo = GoogleSheetResultRepository(gateway, config)
    result = ValidationResult(
        spreadsheet_id="sheet_1",
        summary=ValidationSummary(total_rows=1, valid_rows=1, invalid_rows=0, issues=[]),
    )

    repo.save_result(result)

    gateway.batch_update_values.assert_called_once_with(
        "sheet_1",
        "ValidationResult",
        result.to_rows(),
    )


@pytest.mark.asyncio
async def test_writeback_service_returns_saved_result():
    repo = MagicMock()
    service = WriteBackService(repo)
    summary = ValidationSummary(total_rows=1, valid_rows=1, invalid_rows=0, issues=[])

    with patch("services.writeback_service.check_and_set_idempotency", AsyncMock(return_value=False)):
        result = await service.write_validation_result("sheet_1", summary)

    assert result.spreadsheet_id == "sheet_1"
    assert result.summary == summary
    repo.save_result.assert_called_once_with(result)


# ── ValidateHandler Tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_handler_unauthorized():
    handler = ValidateHandler(MagicMock())
    with patch("handlers.validate_handler.get_user", AsyncMock(return_value=None)):
        result = await handler.handle("U_UNKNOWN")
    
    assert result.type == ResponseType.TEXT
    assert result.text == ACCESS_DENIED


@pytest.mark.asyncio
async def test_validate_handler_success():
    mock_service = MagicMock()
    mock_service.validate_portfolio.return_value = ValidationSummary(
        total_rows=5, valid_rows=5, invalid_rows=0, issues=[]
    )
    handler = ValidateHandler(mock_service)

    with patch("handlers.validate_handler.get_user", AsyncMock(return_value=MOCK_USER)):
        result = await handler.handle("U_ALLOWED")

    assert result.type == ResponseType.RICH
    assert result.contents is not None
    # Verify the flex builder was used successfully by checking bubble structure
    assert result.contents["type"] == "bubble"
    
    # Check that "✅ ข้อมูลถูกต้อง" is in the flex message
    # contents is a dict, we can serialize to string to check easily
    import json
    flex_str = json.dumps(result.contents, ensure_ascii=False)
    assert "✅" in flex_str
    assert "Total" in flex_str


@pytest.mark.asyncio
async def test_validate_handler_writes_result_when_configured():
    mock_validation_service = MagicMock()
    summary = ValidationSummary(total_rows=5, valid_rows=5, invalid_rows=0, issues=[])
    mock_validation_service.validate_portfolio.return_value = summary
    mock_writeback_service = AsyncMock()
    handler = ValidateHandler(mock_validation_service, mock_writeback_service)

    with patch("handlers.validate_handler.get_user", AsyncMock(return_value=MOCK_USER)):
        result = await handler.handle("U_ALLOWED")

    assert result.type == ResponseType.RICH
    mock_writeback_service.write_validation_result.assert_called_once_with(
        MOCK_USER.spreadsheet_id,
        summary,
    )


@pytest.mark.asyncio
async def test_validate_handler_writeback_failure_bubbles_up():
    mock_validation_service = MagicMock()
    summary = ValidationSummary(total_rows=1, valid_rows=1, invalid_rows=0, issues=[])
    mock_validation_service.validate_portfolio.return_value = summary
    mock_writeback_service = AsyncMock()
    mock_writeback_service.write_validation_result.side_effect = RuntimeError("write failed")
    handler = ValidateHandler(mock_validation_service, mock_writeback_service)

    with patch("handlers.validate_handler.get_user", AsyncMock(return_value=MOCK_USER)):
        with pytest.raises(RuntimeError):
            await handler.handle("U_ALLOWED")


@pytest.mark.asyncio
async def test_validate_handler_with_errors():
    from models.validation import ValidationIssue
    mock_service = MagicMock()
    mock_service.validate_portfolio.return_value = ValidationSummary(
        total_rows=5, valid_rows=4, invalid_rows=1, issues=[
            ValidationIssue(row_index=2, symbol="TEST", error_message="Mock Error")
        ]
    )
    handler = ValidateHandler(mock_service)

    with patch("handlers.validate_handler.get_user", AsyncMock(return_value=MOCK_USER)):
        result = await handler.handle("U_ALLOWED")

    assert result.type == ResponseType.RICH
    import json
    flex_str = json.dumps(result.contents, ensure_ascii=False)
    assert "⚠️" in flex_str
    assert "Mock Error" in flex_str
