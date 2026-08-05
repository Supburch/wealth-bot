"""
Validation models.

Used by ValidationService to report issues in the Portfolio sheet.
"""
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

class ValidationIssue(BaseModel):
    """Represents a single validation error for a row."""
    row_index: int
    symbol: str
    error_message: str

class ValidationSummary(BaseModel):
    """Aggregate result of a portfolio validation run."""
    total_rows: int
    valid_rows: int
    invalid_rows: int
    issues: list[ValidationIssue]

    @property
    def is_valid(self) -> bool:
        return self.invalid_rows == 0


class ValidationResultRow(BaseModel):
    """Flat row DTO written to the validation result sheet."""
    run_id: str
    checked_at: datetime
    status: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    row_index: int | None = None
    symbol: str = ""
    error_message: str = ""

    def to_sheet_row(self) -> list[str | int]:
        return [
            self.run_id,
            self.checked_at.isoformat(),
            self.status,
            self.total_rows,
            self.valid_rows,
            self.invalid_rows,
            "" if self.row_index is None else self.row_index,
            self.symbol,
            self.error_message,
        ]


class ValidationResult(BaseModel):
    """Write-back DTO for one validation run."""
    spreadsheet_id: str
    summary: ValidationSummary
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def status(self) -> str:
        return "valid" if self.summary.is_valid else "invalid"

    @property
    def header(self) -> list[str]:
        return [
            "run_id",
            "checked_at",
            "status",
            "total_rows",
            "valid_rows",
            "invalid_rows",
            "row_index",
            "symbol",
            "error_message",
        ]

    def to_rows(self) -> list[list[str | int]]:
        if self.summary.issues:
            detail_rows = [
                ValidationResultRow(
                    run_id=self.run_id,
                    checked_at=self.checked_at,
                    status=self.status,
                    total_rows=self.summary.total_rows,
                    valid_rows=self.summary.valid_rows,
                    invalid_rows=self.summary.invalid_rows,
                    row_index=issue.row_index,
                    symbol=issue.symbol,
                    error_message=issue.error_message,
                ).to_sheet_row()
                for issue in self.summary.issues
            ]
        else:
            detail_rows = [
                ValidationResultRow(
                    run_id=self.run_id,
                    checked_at=self.checked_at,
                    status=self.status,
                    total_rows=self.summary.total_rows,
                    valid_rows=self.summary.valid_rows,
                    invalid_rows=self.summary.invalid_rows,
                ).to_sheet_row()
            ]
        return [self.header, *detail_rows]
