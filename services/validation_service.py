import logging
from decimal import Decimal, InvalidOperation

from core.exceptions import PortfolioReadError
from models.portfolio import PortfolioRow
from models.validation import ValidationIssue, ValidationSummary
from repositories.portfolio_repository import PortfolioRepository

logger = logging.getLogger(__name__)


class ValidationService:
    """Validates the raw Portfolio sheet data."""

    def __init__(self, repository: PortfolioRepository):
        self.repository = repository

    def validate_portfolio(self, spreadsheet_id: str) -> ValidationSummary:
        """
        Fetches rows from the repository and attempts to parse them.
        Returns a ValidationSummary containing any issues found.
        """
        issues: list[ValidationIssue] = []
        valid_rows = 0
        invalid_rows = 0
        total_rows = 0

        try:
            # We fetch raw rows. The repository skips the header.
            fetch = self.repository.fetch_portfolio_rows(spreadsheet_id)
            rows = fetch.rows

            # Short (malformed) rows: flag instead of silently dropping.
            for short in fetch.short_rows:
                total_rows += 1
                invalid_rows += 1
                issues.append(
                    ValidationIssue(
                        row_index=short.row_number,
                        symbol="UNKNOWN",
                        error_message=(
                            f"Row {short.row_number} has only "
                            f"{short.column_count} columns, expected 4 — skipped"
                        ),
                    )
                )

            # Symbols that parse cleanly, for cross-row duplicate detection.
            valid_symbols: list[tuple[int, str]] = []
            for i, row in enumerate(rows):
                total_rows += 1
                sheet_row_num = i + 2

                row_issues = self._validate_row(row)
                if row_issues:
                    invalid_rows += 1
                    for message in row_issues:
                        issues.append(
                            ValidationIssue(
                                row_index=sheet_row_num,
                                symbol=row.symbol or "UNKNOWN",
                                error_message=message,
                            )
                        )
                else:
                    valid_rows += 1
                    valid_symbols.append((sheet_row_num, row.symbol.strip()))

            # Duplicate symbol detection (portfolio-level, cross-row).
            symbol_rows: dict[str, list[int]] = {}
            for sheet_row_num, symbol in valid_symbols:
                key = symbol.casefold()
                symbol_rows.setdefault(key, []).append(sheet_row_num)

            reported: set[str] = set()
            for _, symbol in valid_symbols:
                key = symbol.casefold()
                rows = symbol_rows[key]
                if len(rows) > 1 and key not in reported:
                    reported.add(key)
                    invalid_rows += 1
                    issues.append(
                        ValidationIssue(
                            row_index=0,
                            symbol=symbol,
                            error_message=(
                                f"Duplicate symbol '{symbol}' at rows "
                                f"{', '.join(str(r) for r in sorted(rows))}"
                            ),
                        )
                    )

        except PortfolioReadError as e:
            logger.error(
                "Failed to read portfolio for validation: %s",
                type(e).__name__,
                exc_info=True,
            )
            # If we can't even read the sheet, it's a fatal validation error
            issues.append(
                ValidationIssue(
                    row_index=0,
                    symbol="SYSTEM",
                    error_message="Failed to read Google Sheet"
                )
            )
            # We don't know total rows, so just return what we have
            return ValidationSummary(
                total_rows=0,
                valid_rows=0,
                invalid_rows=1,
                issues=issues
            )
        return ValidationSummary(
            total_rows=total_rows,
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            issues=issues
        )

    def _validate_row(self, row: PortfolioRow) -> list[str]:
        """Validate a single row field-by-field and return error messages."""
        messages: list[str] = []

        if not row.symbol.strip():
            messages.append("Symbol is empty")

        shares_message = self._validate_numeric(
            row.shares,
            field_name="shares",
            display_name="Shares",
            zero_message="Shares cannot be zero",
            negative_message="Shares cannot be negative",
        )
        if shares_message:
            messages.append(shares_message)

        avg_cost_message = self._validate_numeric(
            row.avg_cost,
            field_name="average cost",
            display_name="Average cost",
            zero_message="Prices cannot be zero",
            negative_message="Prices cannot be negative",
        )
        if avg_cost_message:
            messages.append(avg_cost_message)

        current_price_message = self._validate_numeric(
            row.current_price,
            field_name="current price",
            display_name="Current price",
            zero_message="Prices cannot be zero",
            negative_message="Prices cannot be negative",
        )
        if current_price_message:
            messages.append(current_price_message)

        return messages

    @staticmethod
    def _validate_numeric(
        raw: str,
        field_name: str,
        display_name: str,
        zero_message: str,
        negative_message: str,
    ) -> str | None:
        """Validate a numeric field; returns an error message or None if valid."""
        if not raw.strip():
            return f"{display_name} is empty"
        try:
            value = Decimal(raw.replace(",", ""))
        except (InvalidOperation, ValueError):
            return f"Invalid number format for {field_name}"
        if value == 0:
            return zero_message
        if value < 0:
            return negative_message
        return None
