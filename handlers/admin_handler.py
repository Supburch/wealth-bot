from models.response import AppResponse
from core.enums import ResponseType
from core.messages import ACCESS_DENIED, ADMIN_ONLY, UNEXPECTED_ERROR
from services.cache import clear_cache, get_cache_entries_count, get_last_refresh_time, CACHE_TTL
from services.sheets_service import check_sheets_health, invalidate_client
from services.user_mapping_service import get_user


class AdminHandler:
    """Handles admin-only commands: refresh, reload, status."""

    def __init__(self, command: str):
        self.command = command

    async def handle(self, user_id: str) -> AppResponse:
        user_info = await get_user(user_id)
        if not user_info or not user_info.enabled:
            return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)
        if not user_info.is_admin:
            return AppResponse(type=ResponseType.TEXT, text=ADMIN_ONLY)

        if self.command == "refresh":
            await clear_cache()
            return AppResponse(type=ResponseType.TEXT, text="✅ รีเฟรช: ล้างแคชข้อมูลเรียบร้อยแล้ว")

        if self.command == "reload":
            await clear_cache()
            invalidate_client()
            return AppResponse(type=ResponseType.TEXT, text="🔄 โหลดใหม่: ล้างแคชและเชื่อมต่อ Google Sheets ใหม่แล้ว")

        if self.command == "status":
            sheets_ok = await check_sheets_health()
            status_str = "ปกติ" if sheets_ok else "ผิดพลาด"
            text = (
                f"📊 สถานะระบบ\n\n"
                f"ชีต: {status_str}\n"
                f"แคช: ปกติ\n"
                f"รายการ: {get_cache_entries_count()}\n"
                f"รีเฟรชล่าสุด: {get_last_refresh_time()}\n"
                f"อายุแคช: {CACHE_TTL}s"
            )
            return AppResponse(type=ResponseType.TEXT, text=text)

        return AppResponse(type=ResponseType.TEXT, text=UNEXPECTED_ERROR)

