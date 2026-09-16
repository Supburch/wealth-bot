import logging

from models.response import AppResponse
from core.enums import ResponseType
from core.exceptions import SheetsReadError
from core.messages import ACCESS_DENIED, DATA_UPDATING
from services.portfolio_service import allocation_balance_check, get_asset_allocation
from services.user_mapping_service import get_user
from services.chart_service import get_cached_chart_url

logger = logging.getLogger(__name__)


class AllocationHandler:
    """Returns asset allocation (สัดส่วน): value + weight per asset class."""

    async def handle(self, user_id: str) -> AppResponse:
        user_info = await get_user(user_id)
        if not user_info or not user_info.enabled:
            return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

        try:
            allocation = await get_asset_allocation(user_info)
        except SheetsReadError:
            return AppResponse(type=ResponseType.TEXT, text=DATA_UPDATING)

        if allocation is None or allocation.is_empty:
            return AppResponse(type=ResponseType.TEXT, text="ไม่พบข้อมูลสัดส่วนพอร์ต")

        lines = "\n".join(
            f"{e.name}: {e.percent:.1f}% (฿{e.value:,.0f})" for e in allocation.entries
        )
        text = f"📊 สัดส่วนพอร์ต\n\n{lines}\n\nรวม: ฿{allocation.total:,.0f}"
        within, total = allocation_balance_check(allocation)
        if not within:
            text += f"\n⚠️ รวมสัดส่วนไม่ครบ 100% ({total:.1f}%)"

        image_url = await self._build_chart_url(allocation)
        return AppResponse(type=ResponseType.TEXT, text=text, image_url=image_url)

    async def _build_chart_url(self, allocation) -> str | None:
        """Build the asset-allocation pie-chart URL, degrading gracefully.

        Chart generation is best-effort: any failure (bad values, cache errors)
        is logged and returns ``None`` so the numeric reply is still delivered.
        """
        try:
            labels = [e.name for e in allocation.entries]
            values = [float(e.value) for e in allocation.entries]
            return await get_cached_chart_url("pie", labels, values)
        except Exception:
            logger.warning("Failed to build allocation chart URL", exc_info=True)
            return None
