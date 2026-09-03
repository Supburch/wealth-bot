from models.response import AppResponse
from core.enums import ResponseType
from core.messages import ACCESS_DENIED
from services.portfolio_service import get_cash_balance
from services.user_mapping_service import get_user


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
    """Returns available cash from the AssetAllocation sheet (Cash entry)."""

    async def handle(self, user_id: str) -> AppResponse:
        user_info = await get_user(user_id)
        if not user_info or not user_info.enabled:
            return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

        cash = await get_cash_balance(user_info)
        text = f"💵 เงินสด\n\n฿{cash:,.0f}"
        return AppResponse(type=ResponseType.TEXT, text=text)
