"""Drill-down handler: 'เจาะดู {category}' returns a breakdown of one asset category."""

from models.response import AppResponse
from models.portfolio import AssetBreakdown
from core.enums import ResponseType
from core.exceptions import SheetsReadError
from core.messages import ACCESS_DENIED, DATA_UPDATING
from services.portfolio_service import get_asset_breakdown
from services.user_mapping_service import get_user

BREAKDOWN_PREFIX = "เจาะดู "

NO_BREAKDOWN_DATA = "ยังไม่มีข้อมูลรายละเอียดของหมวดนี้"


class AssetBreakdownHandler:
    """Returns a formatted breakdown for a single asset category."""

    def __init__(self, category: str):
        self.category = category

    async def handle(self, user_id: str) -> AppResponse:
        user_info = await get_user(user_id)
        if not user_info or not user_info.enabled:
            return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

        try:
            breakdown = await get_asset_breakdown(user_info, self.category)
        except SheetsReadError:
            return AppResponse(type=ResponseType.TEXT, text=DATA_UPDATING)

        if breakdown.is_empty:
            return AppResponse(type=ResponseType.TEXT, text=NO_BREAKDOWN_DATA)

        return AppResponse(type=ResponseType.TEXT, text=_format_breakdown(breakdown))


def _format_breakdown(breakdown: AssetBreakdown) -> str:
    lines = [f"🔍 {breakdown.category} (รวม ฿{breakdown.total:,.0f})"]
    if breakdown.items:
        name_width = max(len(item.name) for item in breakdown.items) + 3
        for item in breakdown.items:
            label = f"{item.name}:".ljust(name_width)
            lines.append(f"{label}฿{item.value:,.0f}  ({item.percent:.1f}%)")
    return "\n".join(lines)


async def handle_asset_breakdown(user_id: str, command: str) -> AppResponse:
    """Prefix dispatcher: extract the category from 'เจาะดู {category}'."""
    category = command[len(BREAKDOWN_PREFIX):].strip()
    return await AssetBreakdownHandler(category).handle(user_id)
