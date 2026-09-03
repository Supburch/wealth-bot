from models.response import AppResponse
from core.enums import ResponseType


class TodayHandler:
    """Deprecated. 'วันนี้' was removed from the menu because daily P&L data is
    not available in the source sheets. Points users to 'สรุป' instead."""

    async def handle(self, user_id: str) -> AppResponse:
        return AppResponse(
            type=ResponseType.TEXT,
            text="คำสั่ง 'วันนี้' ถูกยกเลิกแล้ว\nใช้ 'สรุป' หรือ 'สัดส่วน' แทนครับ",
        )
