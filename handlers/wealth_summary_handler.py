import logging
from models.response import AppResponse
from core.enums import ResponseType
from core.messages import ACCESS_DENIED, UNEXPECTED_ERROR
from services.portfolio_service import get_wealth_summary
from services.user_mapping_service import get_user

logger = logging.getLogger(__name__)


def _fmt(num: float, is_currency: bool = False) -> str:
    if is_currency and num >= 1_000_000:
        return f"{num / 1_000_000:.2f}M"
    if is_currency and num >= 1_000:
        return f"{num / 1_000:.0f}K"
    return f"{num:,.0f}"


class WealthSummaryHandler:
    """Returns a composite portfolio + top holdings summary."""

    async def handle(self, user_id: str) -> AppResponse:
        try:
            user_info = await get_user(user_id)
            if not user_info or not user_info.enabled:
                return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

            data = await get_wealth_summary(user_info)
            sign = "+" if data.summary.profit >= 0 else ""
            top = "\n".join(h.symbol for h in data.top_holdings)
            text = (
                f"💰 Wealth Summary\n"
                f"Portfolio Value:\n฿{_fmt(data.summary.portfolio_value, True)}\n"
                f"Profit:\n{sign}{data.summary.profit_pct}%\n"
                f"Cash:\n฿{_fmt(data.summary.cash, True)}\n"
                f"Top Holdings:\n{top}"
            )
            return AppResponse(type=ResponseType.TEXT, text=text)
        except Exception:
            logger.exception("Unexpected error in WealthSummaryHandler")
            return AppResponse(type=ResponseType.TEXT, text=UNEXPECTED_ERROR)
