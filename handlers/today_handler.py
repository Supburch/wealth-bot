import logging
from models.response import AppResponse
from core.enums import ResponseType
from core.messages import ACCESS_DENIED, UNEXPECTED_ERROR
from services.portfolio_service import get_today_summary
from services.user_mapping_service import get_user
from builders.today_flex_builder import build_today_flex

logger = logging.getLogger(__name__)


class TodayHandler:
    """Returns today's portfolio performance as a Flex Message."""

    async def handle(self, user_id: str) -> AppResponse:
        try:
            user_info = await get_user(user_id)
            if not user_info or not user_info.enabled:
                return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

            data = await get_today_summary(user_info)
            contents = build_today_flex(data)
            return AppResponse(
                type=ResponseType.RICH,
                alt_text="กำไรวันนี้",
                contents=contents,
            )
        except Exception:
            logger.exception("Unexpected error in TodayHandler")
            return AppResponse(type=ResponseType.TEXT, text=UNEXPECTED_ERROR)
