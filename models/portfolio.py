from decimal import Decimal
from pydantic import BaseModel, model_validator
from core.constants import TWOPLACES

class PortfolioRow(BaseModel):
    symbol: str
    avg_cost: str
    shares: str
    current_price: str

class PortfolioItem(BaseModel):
    symbol: str
    avg_cost: Decimal
    shares: Decimal
    current_price: Decimal
    
    @model_validator(mode="after")
    def validate_positive_values(self) -> "PortfolioItem":
        if self.shares < 0:
            raise ValueError(f"Shares cannot be negative for {self.symbol}")
        if self.avg_cost < 0 or self.current_price < 0:
            raise ValueError(f"Prices cannot be negative for {self.symbol}")
        return self
        
    @property
    def market_value(self) -> Decimal:
        return (self.shares * self.current_price).quantize(TWOPLACES)
        
    @property
    def total_cost(self) -> Decimal:
        return (self.shares * self.avg_cost).quantize(TWOPLACES)
        
    @property
    def profit(self) -> Decimal:
        return self.market_value - self.total_cost

class PortfolioSummary(BaseModel):
    items: list[PortfolioItem]
    
    @property
    def total_market_value(self) -> Decimal:
        return sum((item.market_value for item in self.items), Decimal("0.00"))
        
    @property
    def total_cost(self) -> Decimal:
        return sum((item.total_cost for item in self.items), Decimal("0.00"))
        
    @property
    def total_profit(self) -> Decimal:
        return self.total_market_value - self.total_cost
        
    @property
    def roi_percent(self) -> Decimal:
        if self.total_cost == 0:
            return Decimal("0.00")
        return ((self.total_profit / self.total_cost) * 100).quantize(TWOPLACES)
        
    @property
    def total_positions(self) -> int:
        return len(self.items)
        
    @property
    def is_empty(self) -> bool:
        return len(self.items) == 0
