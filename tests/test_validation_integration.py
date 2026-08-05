import os

import pytest

from core.config import AppConfig
from models.validation import ValidationIssue, ValidationResult, ValidationSummary
from repositories.validation_result_repository import GoogleSheetResultRepository


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
