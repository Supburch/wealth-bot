from models.validation import ValidationResult, ValidationSummary
from repositories.validation_result_repository import ValidationResultRepository


class WriteBackService:
    """Coordinates write-back of validation summaries."""

    def __init__(self, result_repository: ValidationResultRepository):
        self.result_repository = result_repository

    def write_validation_result(
        self,
        spreadsheet_id: str,
        summary: ValidationSummary,
    ) -> ValidationResult:
        result = ValidationResult(spreadsheet_id=spreadsheet_id, summary=summary)
        self.result_repository.save_result(result)
        return result
