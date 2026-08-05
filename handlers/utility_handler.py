import logging
from models.response import AppResponse
from core.enums import ResponseType
from core.messages import ACCESS_DENIED, UNEXPECTED_ERROR
from services.portfolio_service import get_portfolio_summary
from services.user_mapping_service import get_user

logger = logging.getLogger(__name__)


class PingHandler:
    """Liveness check — returns pong."""

    async def handle(self, user_id: str) -> AppResponse:
        return AppResponse(type=ResponseType.TEXT, text="pong")


class VersionHandler:
    """Returns the bot version string."""

    def __init__(self, version: str):
        self.version = version

    async def handle(self, user_id: str) -> AppResponse:
        return AppResponse(type=ResponseType.TEXT, text=f"Wealth Bot\nv{self.version}")


class CashHandler:
    """Returns available cash from the PortfolioSummary sheet."""

    async def handle(self, user_id: str) -> AppResponse:
        try:
            user_info = await get_user(user_id)
            if not user_info or not user_info.enabled:
                return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

            data = await get_portfolio_summary(user_info)
            text = f"💵 เงินสด\n\n฿{data.cash:,.0f}"
            return AppResponse(type=ResponseType.TEXT, text=text)
        except Exception:
            logger.exception("Unexpected error in CashHandler")
            return AppResponse(type=ResponseType.TEXT, text=UNEXPECTED_ERROR)
