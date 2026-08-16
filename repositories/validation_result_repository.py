import logging
from typing import Protocol, Sequence

from core.sheet_config import AppConfig
from models.validation import ValidationResult

logger = logging.getLogger(__name__)


class ValidationResultRepository(Protocol):
    """Persistence boundary for validation result write-back."""

    def save_result(self, result: ValidationResult) -> None:
        ...


class ValidationResultGateway(Protocol):
    def batch_update_values(
        self,
        spreadsheet_id: str,
        sheet_title: str,
        rows: Sequence[Sequence[str | int]],
    ) -> None:
        ...


class GoogleSheetResultRepository:
    """Stores validation result rows in a dedicated Google Sheet tab."""

    def __init__(self, sheets_gateway: ValidationResultGateway, config: AppConfig):
        self.sheets_gateway = sheets_gateway
        self.config = config

    def save_result(self, result: ValidationResult) -> None:
        try:
            self.sheets_gateway.batch_update_values(
                result.spreadsheet_id,
                self.config.validation_result_sheet,
                result.to_rows(),
            )
        except Exception:
            logger.exception(
                "Failed to write validation result",
                extra={"spreadsheet_id": result.spreadsheet_id},
            )
            raise
