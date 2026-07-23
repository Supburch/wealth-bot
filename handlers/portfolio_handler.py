import logging
from handlers.base import CommandHandler
from models.response import AppResponse
from core.enums import ResponseType
from core.messages import (
    EMPTY_PORTFOLIO, ACCESS_DENIED, 
    PORTFOLIO_READ_ERROR, PORTFOLIO_PARSE_ERROR, UNEXPECTED_ERROR
)
from services.portfolio_service import PortfolioService
from services.user_mapping_service import get_user
from core.exceptions import PortfolioReadError, PortfolioParseError

logger = logging.getLogger(__name__)

class PortfolioHandler:
    def __init__(self, portfolio_service: PortfolioService):
        self.portfolio_service = portfolio_service

    async def handle(self, user_id: str) -> AppResponse:
        try:
            user_info = await get_user(user_id)
            if not user_info or not user_info.enabled:
                return AppResponse(text=ACCESS_DENIED)
                
            result = self.portfolio_service.get_portfolio(user_info.spreadsheet_id)
            
            if not result.is_success:
                return AppResponse(text=result.error or UNEXPECTED_ERROR)
                
            portfolio = result.data
            if portfolio.is_empty:
                return AppResponse(text=EMPTY_PORTFOLIO)
                
            sign_profit = "+" if portfolio.total_profit >= 0 else ""
            reply_text = (
                f"💰 Portfolio\n"
                f"มูลค่าพอร์ต:\n฿{portfolio.total_market_value:,.0f}\n"
                f"ต้นทุน:\n฿{portfolio.total_cost:,.0f}\n"
                f"กำไร:\n{sign_profit}฿{portfolio.total_profit:,.0f}\n"
                f"ผลตอบแทน:\n{sign_profit}{portfolio.roi_percent}%"
            )
            return AppResponse(text=reply_text)
            
        except PortfolioReadError:
            return AppResponse(text=PORTFOLIO_READ_ERROR)
        except PortfolioParseError:
            return AppResponse(text=PORTFOLIO_PARSE_ERROR)
        except Exception as e:
            logger.exception("Unexpected error in PortfolioHandler")
            return AppResponse(text=UNEXPECTED_ERROR)
