from models.response import AppResponse
from core.enums import ResponseType
from core.messages import ACCESS_DENIED, UNKNOWN_COMMAND
from services.portfolio_service import get_holding_breakdown
from services.user_mapping_service import get_user


async def handle_symbol_lookup(user_id: str, symbol: str) -> AppResponse:
    """
    Fallback handler: look up a holding by symbol string.
    Called by CommandRouter when no named command matches.
    """
    user_info = await get_user(user_id)
    if not user_info or not user_info.enabled:
        return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

    breakdown = await get_holding_breakdown(user_info, symbol)
    if breakdown:
        sign = "+" if breakdown.profit_pct >= 0 else ""
        text = (
            f"{breakdown.symbol}\n\n"
            f"มูลค่า:\n฿{breakdown.market_value:,.0f}\n\n"
            f"สัดส่วนในพอร์ต:\n{breakdown.weight:g}%\n\n"
            f"ต้นทุน:\n฿{breakdown.cost:,.0f}\n\n"
            f"ผลตอบแทน:\n{sign}{breakdown.profit_pct}%"
        )
        return AppResponse(type=ResponseType.TEXT, text=text)

    return AppResponse(type=ResponseType.TEXT, text=UNKNOWN_COMMAND)
