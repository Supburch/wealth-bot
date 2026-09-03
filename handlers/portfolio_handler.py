import asyncio
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
            return AppResponse(
                type=ResponseType.RICH,
                alt_text="สรุปพอร์ต",
                contents=output,
            )

        except SheetsReadError:
            return AppResponse(type=ResponseType.TEXT, text=FX_RATE_ERROR)
        except PortfolioParseError:
            return AppResponse(type=ResponseType.TEXT, text=FX_RATE_ERROR)
        except PortfolioReadError:
            return AppResponse(type=ResponseType.TEXT, text=PORTFOLIO_READ_ERROR)
