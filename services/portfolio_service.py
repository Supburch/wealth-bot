import logging
from decimal import Decimal, InvalidOperation
from typing import List, Generic, TypeVar
from pydantic import ValidationError
from core.exceptions import PortfolioParseError, PortfolioReadError
from models.portfolio import PortfolioRow, PortfolioItem, PortfolioSummary
from repositories.portfolio_repository import PortfolioRepository
from enum import IntEnum

logger = logging.getLogger(__name__)

T = TypeVar('T')

class ServiceResult(Generic[T]):
    def __init__(self, data: T | None = None, error: str | None = None):
        self.data = data
        self.error = error

    @property
    def is_success(self) -> bool:
        return self.error is None

class PortfolioColumn(IntEnum):
    SYMBOL = 0
    AVG_COST = 1
    SHARES = 2
    CURRENT_PRICE = 3

class PortfolioService:
    def __init__(self, repository: PortfolioRepository):
        self.repository = repository

    def get_portfolio(self, spreadsheet_id: str, strict: bool = False) -> ServiceResult[PortfolioSummary]:
        try:
            rows = self.repository.fetch_portfolio_rows(spreadsheet_id)
            items = []
            
            for row in rows:
                try:
                    item = PortfolioItem(
                        symbol=row.symbol,
                        avg_cost=Decimal(row.avg_cost.replace(',', '')),
                        shares=Decimal(row.shares.replace(',', '')),
                        current_price=Decimal(row.current_price.replace(',', ''))
                    )
                    items.append(item)
                except (InvalidOperation, ValidationError, ValueError) as e:
                    logger.warning("Skipping invalid row", extra={"symbol": row.symbol, "error": str(e)})
                    if strict:
                        raise PortfolioParseError(f"Error parsing row for symbol {row.symbol}: {e}") from e
                        
            return ServiceResult(data=PortfolioSummary(items=items))
            
        except PortfolioReadError as e:
            return ServiceResult(error=str(e))
        except PortfolioParseError as e:
            return ServiceResult(error=str(e))
        except Exception as e:
            logger.exception("Unexpected error in get_portfolio")
            return ServiceResult(error="Internal service error")
