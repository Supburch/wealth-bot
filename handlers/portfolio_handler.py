import logging
from models.response import AppResponse
from core.enums import ResponseType
from core.messages import (
    EMPTY_PORTFOLIO, ACCESS_DENIED,
    PORTFOLIO_READ_ERROR, PORTFOLIO_PARSE_ERROR, UNEXPECTED_ERROR
)
from services.portfolio_service import PortfolioService
from services.user_mapping_service import get_user
from core.exceptions import PortfolioReadError, PortfolioParseError
from builders.portfolio_flex_builder import build_portfolio_flex

logger = logging.getLogger(__name__)

class PortfolioHandler:
    def __init__(self, portfolio_service: PortfolioService):
        self.portfolio_service = portfolio_service

    async def handle(self, user_id: str) -> AppResponse:
        try:
            user_info = await get_user(user_id)
            if not user_info or not user_info.enabled:
                return AppResponse(type=ResponseType.TEXT, text=ACCESS_DENIED)

            result = self.portfolio_service.get_portfolio(user_info.spreadsheet_id)

            if not result.is_success:
                return AppResponse(type=ResponseType.TEXT, text=result.error or UNEXPECTED_ERROR)

            portfolio = result.data
            if portfolio.is_empty:
                return AppResponse(type=ResponseType.TEXT, text=EMPTY_PORTFOLIO)

            contents = build_portfolio_flex(portfolio)
            return AppResponse(
                type=ResponseType.RICH,
                alt_text="Portfolio Summary",
                text="Portfolio Summary",
                contents=contents
            )

        except PortfolioReadError:
            return AppResponse(type=ResponseType.TEXT, text=PORTFOLIO_READ_ERROR)
        except PortfolioParseError:
            return AppResponse(type=ResponseType.TEXT, text=PORTFOLIO_PARSE_ERROR)
        except Exception:
            logger.exception("Unexpected error in PortfolioHandler")
            return AppResponse(type=ResponseType.TEXT, text=UNEXPECTED_ERROR)
