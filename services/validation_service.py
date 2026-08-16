import logging
from decimal import Decimal, InvalidOperation
from pydantic import ValidationError

from core.exceptions import PortfolioReadError
from models.portfolio import PortfolioItem
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
            rows = self.repository.fetch_portfolio_rows(spreadsheet_id)
            
            # The repository index is 0-based for the data rows. 
            # In Sheets, row 1 is header, row 2 is first data row.
            # So actual sheet row is approx `index + 2`.
            for i, row in enumerate(rows):
                total_rows += 1
                sheet_row_num = i + 2
                
                try:
                    PortfolioItem(
                        symbol=row.symbol,
                        avg_cost=Decimal(row.avg_cost.replace(",", "")),
                        shares=Decimal(row.shares.replace(",", "")),
                        current_price=Decimal(row.current_price.replace(",", "")),
                    )
                    valid_rows += 1
                except (InvalidOperation, ValueError) as e:
                    invalid_rows += 1
                    if isinstance(e, InvalidOperation):
                        error_str = "Invalid number format (letters or special characters found)"
                    else:
                        error_str = str(e)
                        if "could not convert" in error_str or "invalid literal" in error_str:
                             error_str = "Invalid number format (letters or special characters found)"
                    
                    issues.append(
                        ValidationIssue(
                            row_index=sheet_row_num,
                            symbol=row.symbol or "UNKNOWN",
                            error_message=error_str
                        )
                    )
                except ValidationError as e:
                    invalid_rows += 1
                    # Pydantic validation error (e.g. negative shares/prices)
                    # Extract the first error message
                    err_msg = e.errors()[0].get("msg", str(e))
                    
                    # Clean up common pydantic messages
                    if "Value error, " in err_msg:
                        err_msg = err_msg.replace("Value error, ", "")

                    issues.append(
                        ValidationIssue(
                            row_index=sheet_row_num,
                            symbol=row.symbol or "UNKNOWN",
                            error_message=err_msg
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
        except Exception:
            logger.exception("Unexpected error during validation")
            issues.append(
                ValidationIssue(
                    row_index=0,
                    symbol="SYSTEM",
                    error_message="Unexpected system error during validation."
                )
            )
            return ValidationSummary(
                total_rows=total_rows,
                valid_rows=valid_rows,
                invalid_rows=invalid_rows + 1,
                issues=issues
            )

        return ValidationSummary(
            total_rows=total_rows,
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            issues=issues
        )
