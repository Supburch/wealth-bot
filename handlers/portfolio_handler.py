import asyncio
import logging

from models.response import AppResponse
from core.enums import ResponseType
from core.messages import (
    EMPTY_PORTFOLIO, ACCESS_DENIED,
    PORTFOLIO_READ_ERROR, UNEXPECTED_ERROR,
    FX_RATE_ERROR,
)
from services.portfolio_service import PortfolioService, get_fx_rate_thb_per_usd
from services.user_mapping_service import get_user
from core.exceptions import PortfolioReadError, PortfolioParseError, SheetsReadError
from builders.portfolio_flex_builder import build_portfolio_flex
from services.chart_service import get_cached_chart_url

logger = logging.getLogger(__name__)


class PortfolioHandler:
    def __init__(self, portfolio_service: PortfolioService):
        self.portfolio_service = portfolio_service

    async def handle(self, user_id: str) -> AppResponse:
        try:
            user_info = await get_user(user_id)
            if not user_info or not user_info.enabled:
                return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

            fx_rate = await get_fx_rate_thb_per_usd(user_info)

            result = await asyncio.to_thread(
                self.portfolio_service.get_portfolio, user_info.spreadsheet_id, False, fx_rate
            )

            if not result.is_success:
                return AppResponse(type=ResponseType.TEXT, text=result.error or UNEXPECTED_ERROR)

            portfolio = result.data
            if portfolio.is_empty:
                return AppResponse(type=ResponseType.TEXT, text=EMPTY_PORTFOLIO)

            output = build_portfolio_flex(portfolio, fx_rate=fx_rate)
            image_url = await self._build_chart_url(portfolio)
            return AppResponse(
                type=ResponseType.RICH,
                alt_text="สรุปพอร์ต",
                contents=output,
                image_url=image_url,
            )

        except SheetsReadError:
            return AppResponse(type=ResponseType.TEXT, text=FX_RATE_ERROR)
        except PortfolioParseError:
            return AppResponse(type=ResponseType.TEXT, text=FX_RATE_ERROR)
        except PortfolioReadError:
            return AppResponse(type=ResponseType.TEXT, text=PORTFOLIO_READ_ERROR)

    async def _build_chart_url(self, portfolio) -> str | None:
        """Build the Stock USA vs Stock DR bar-chart URL, degrading gracefully.

        Chart generation is best-effort: any failure (bad values, cache errors)
        is logged and returns ``None`` so the numeric reply is still delivered.
        """
        try:
            labels = ["Stock USA", "Stock DR"]
            values = [float(portfolio.us_value), float(portfolio.dr_value)]
            return await get_cached_chart_url("bar", labels, values)
        except Exception:
            logger.warning("Failed to build portfolio chart URL", exc_info=True)
            return None
