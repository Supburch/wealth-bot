import logging
from models.response import AppResponse
from core.enums import ResponseType
from core.messages import ACCESS_DENIED, UNEXPECTED_ERROR
from services.portfolio_service import get_asset_allocation
from services.user_mapping_service import get_user

logger = logging.getLogger(__name__)


class AllocationHandler:
    """Returns asset allocation (สัดส่วน). Placeholder until sheet schema confirmed."""

    async def handle(self, user_id: str) -> AppResponse:
        try:
            user_info = await get_user(user_id)
            if not user_info or not user_info.enabled:
                return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

            allocation = await get_asset_allocation(user_info)
            if not allocation:
                return AppResponse(type=ResponseType.TEXT, text="ไม่พบข้อมูลสัดส่วนพอร์ต")

            lines = "\n".join(f"{k}: {v}%" for k, v in allocation.items())
            text = f"📊 สัดส่วนพอร์ต\n\n{lines}"
            return AppResponse(type=ResponseType.TEXT, text=text)
        except Exception:
            logger.exception("Unexpected error in AllocationHandler")
            return AppResponse(type=ResponseType.TEXT, text=UNEXPECTED_ERROR)
