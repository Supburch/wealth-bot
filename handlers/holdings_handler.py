from models.response import AppResponse
from core.enums import ResponseType
from core.messages import ACCESS_DENIED
from services.portfolio_service import get_top_holdings, get_all_holdings
from services.user_mapping_service import get_user
from builders.holdings_flex_builder import build_holdings_flex


class HoldingsHandler:
    """Top holdings sorted by weight (คำสั่ง ถืออะไร / top)."""

    async def handle(self, user_id: str) -> AppResponse:
        user_info = await get_user(user_id)
        if not user_info or not user_info.enabled:
            return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

        holdings = await get_top_holdings(user_info)
        contents = build_holdings_flex(holdings, title="📋 ถืออะไร")
        return AppResponse(type=ResponseType.RICH, alt_text="Top Holdings", contents=contents)


class WinnersHandler:
    """Top performers sorted by profit_pct descending (คำสั่ง winners)."""

    async def handle(self, user_id: str) -> AppResponse:
        user_info = await get_user(user_id)
        if not user_info or not user_info.enabled:
            return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

        holdings = await get_all_holdings(user_info)
        winners = sorted(holdings, key=lambda h: h.profit_pct, reverse=True)
        contents = build_holdings_flex(winners, title="🏆 Winners")
        return AppResponse(type=ResponseType.RICH, alt_text="Winners", contents=contents)


class LosersHandler:
    """Worst performers sorted by profit_pct ascending (คำสั่ง losers)."""

    async def handle(self, user_id: str) -> AppResponse:
        user_info = await get_user(user_id)
        if not user_info or not user_info.enabled:
            return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

        holdings = await get_all_holdings(user_info)
        losers = sorted(holdings, key=lambda h: h.profit_pct)
        contents = build_holdings_flex(losers, title="📉 Losers")
        return AppResponse(type=ResponseType.RICH, alt_text="Losers", contents=contents)
