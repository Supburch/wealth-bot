from decimal import Decimal

from models.response import AppResponse
from core.enums import ResponseType
from core.exceptions import SheetsReadError
from core.messages import ACCESS_DENIED, DATA_UPDATING
from services.portfolio_service import get_asset_allocation
from services.user_mapping_service import get_user


class WealthSummaryHandler:
    """Returns a portfolio summary derived from the AssetAllocation sheet (source of truth)."""

    async def handle(self, user_id: str) -> AppResponse:
        user_info = await get_user(user_id)
        if not user_info or not user_info.enabled:
            return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

        try:
            allocation = await get_asset_allocation(user_info)
        except SheetsReadError:
            return AppResponse(type=ResponseType.TEXT, text=DATA_UPDATING)

        if allocation is None or allocation.is_empty:
            return AppResponse(type=ResponseType.TEXT, text="ไม่พบข้อมูลพอร์ต")

        cash = Decimal("0")
        for entry in allocation.entries:
            if entry.name.strip().lower() == "cash":
                cash = entry.value
                break

        lines = "\n".join(
            f"• {e.name} — {e.percent:.1f}% (฿{e.value:,.0f})"
            for e in allocation.entries
        )
        text = (
            "💰 สรุปพอร์ต\n\n"
            f"มูลค่าพอร์ตรวม: ฿{allocation.total:,.0f}\n"
            f"เงินสด: ฿{cash:,.0f}\n\n"
            "สัดส่วนสินทรัพย์:\n"
            f"{lines}"
        )
        return AppResponse(type=ResponseType.TEXT, text=text)
