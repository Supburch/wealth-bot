import asyncio
from models.response import AppResponse
from core.enums import ResponseType
from core.messages import ACCESS_DENIED
from services.validation_service import ValidationService
from services.writeback_service import WriteBackService
from services.user_mapping_service import get_user
from builders.validation_flex_builder import build_validation_flex


class ValidateHandler:
    """Validates the raw Portfolio sheet and returns a report."""

    def __init__(
        self,
        validation_service: ValidationService,
        writeback_service: WriteBackService | None = None,
    ):
        self.validation_service = validation_service
        self.writeback_service = writeback_service

    async def handle(self, user_id: str) -> AppResponse:
        user_info = await get_user(user_id)
        if not user_info or not user_info.enabled:
            return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

        summary = await asyncio.to_thread(
            self.validation_service.validate_portfolio, user_info.spreadsheet_id
        )
        if self.writeback_service:
            await self.writeback_service.write_validation_result(
                user_info.spreadsheet_id,
                summary,
            )

        contents = build_validation_flex(summary)
        return AppResponse(
            type=ResponseType.RICH, 
            alt_text="ผลการตรวจสอบข้อมูล (Validation)", 
            contents=contents
        )
