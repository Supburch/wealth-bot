import os
import time

import pytest

from core.config import AppConfig
from models.validation import ValidationIssue, ValidationResult, ValidationSummary
from repositories.validation_result_repository import GoogleSheetResultRepository
from services.writeback_service import WriteBackService
from services.cache import clear_cache


@pytest.fixture(autouse=True)
async def reset_idempotency_cache():
    await clear_cache()
    yield
    await clear_cache()


@pytest.mark.skipif(
    os.getenv("RUN_GOOGLE_SHEETS_INTEGRATION") != "1",
    reason="Set RUN_GOOGLE_SHEETS_INTEGRATION=1 and INTEGRATION_SPREADSHEET_ID to run.",
)
def test_google_sheet_result_repository_writes_to_real_sheet():
    from services.sheets_service import batch_update_values, get_raw_range

    spreadsheet_id = os.environ["INTEGRATION_SPREADSHEET_ID"]

    class Gateway:
        def batch_update_values(self, spreadsheet_id, sheet_title, rows):
            batch_update_values(spreadsheet_id, sheet_title, rows)

    config = AppConfig(validation_result_sheet="ValidationResultIntegration")
    repo = GoogleSheetResultRepository(Gateway(), config)
    result = ValidationResult(
        spreadsheet_id=spreadsheet_id,
        summary=ValidationSummary(
            total_rows=1,
            valid_rows=0,
            invalid_rows=1,
            issues=[
                ValidationIssue(
                    row_index=2,
                    symbol="TEST",
                    error_message="Integration test write-back",
                )
            ],
        ),
        run_id="integration-test",
    )

    repo.save_result(result)

    rows = get_raw_range(spreadsheet_id, "ValidationResultIntegration!A1:I2")
    assert rows[0] == result.header
    assert rows[1][0] == "integration-test"
    assert rows[1][2] == "invalid"


@pytest.mark.asyncio
async def test_writeback_service_async_with_delayed_repository():
    """Async integration: WriteBackService offloads sync I/O without blocking the event loop."""
    summary = ValidationSummary(
        total_rows=1,
        valid_rows=1,
        invalid_rows=0,
        issues=[],
    )
    saved: list[ValidationResult] = []

    class DelayedRepository:
        def save_result(self, result: ValidationResult) -> None:
            time.sleep(0.05)
            saved.append(result)

    service = WriteBackService(DelayedRepository())
    started = time.perf_counter()
    result = await service.write_validation_result("integration-sheet", summary)
    elapsed = time.perf_counter() - started

    assert result is not None
    assert result.summary == summary
    assert len(saved) == 1
    assert saved[0].spreadsheet_id == "integration-sheet"
    assert elapsed >= 0.04


@pytest.mark.skipif(
    os.getenv("RUN_GOOGLE_SHEETS_INTEGRATION") != "1",
    reason="Set RUN_GOOGLE_SHEETS_INTEGRATION=1 and INTEGRATION_SPREADSHEET_ID to run.",
)
@pytest.mark.asyncio
async def test_writeback_service_writes_to_real_sheet_async():
    from services.sheets_service import batch_update_values, get_raw_range

    spreadsheet_id = os.environ["INTEGRATION_SPREADSHEET_ID"]

    class Gateway:
        def batch_update_values(self, spreadsheet_id, sheet_title, rows):
            batch_update_values(spreadsheet_id, sheet_title, rows)

    config = AppConfig(validation_result_sheet="ValidationResultIntegration")
    repo = GoogleSheetResultRepository(Gateway(), config)
    service = WriteBackService(repo)
    summary = ValidationSummary(
        total_rows=1,
        valid_rows=0,
        invalid_rows=1,
        issues=[
            ValidationIssue(
                row_index=2,
                symbol="ASYNC",
                error_message="Async integration test write-back",
            )
        ],
    )

    result = await service.write_validation_result(spreadsheet_id, summary)

    assert result is not None
    rows = get_raw_range(spreadsheet_id, "ValidationResultIntegration!A1:I2")
    assert rows[1][2] == "invalid"
    assert rows[1][7] == "ASYNC"
