from models.response import AppResponse
from core.enums import ResponseType
from core.messages import ACCESS_DENIED
from services.portfolio_service import allocation_balance_check, get_asset_allocation
from services.user_mapping_service import get_user


class AllocationHandler:
    """Returns asset allocation (สัดส่วน): value + weight per asset class."""

    async def handle(self, user_id: str) -> AppResponse:
        user_info = await get_user(user_id)
        if not user_info or not user_info.enabled:
            return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

        allocation = await get_asset_allocation(user_info)
        if allocation is None or allocation.is_empty:
            return AppResponse(type=ResponseType.TEXT, text="ไม่พบข้อมูลสัดส่วนพอร์ต")

        lines = "\n".join(
            f"{e.name}: {e.percent:.1f}% (฿{e.value:,.0f})" for e in allocation.entries
        )
        text = f"📊 สัดส่วนพอร์ต\n\n{lines}\n\nรวม: ฿{allocation.total:,.0f}"
        within, total = allocation_balance_check(allocation)
        if not within:
            text += f"\n⚠️ รวมสัดส่วนไม่ครบ 100% ({total:.1f}%)"
        return AppResponse(type=ResponseType.TEXT, text=text)
