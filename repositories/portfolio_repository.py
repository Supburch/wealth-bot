import logging
from dataclasses import dataclass
from typing import Protocol, List
from core.sheet_config import AppConfig
from core.exceptions import PortfolioReadError
from core.redaction import mask_id
from models.portfolio import PortfolioRow

logger = logging.getLogger(__name__)


@dataclass
class ShortRow:
    """A data row with fewer columns than expected (malformed)."""
    row_number: int
    column_count: int


@dataclass
class PortfolioFetchResult:
    """Complete parsed rows plus short-row metadata for validation."""
    rows: List[PortfolioRow]
    short_rows: List[ShortRow]


class SheetsGateway(Protocol):
    def get_sheet_records(self, spreadsheet_id: str, range_name: str) -> List[List[str]]:
        ...

class PortfolioRepository:
    def __init__(self, sheets_gateway: SheetsGateway, config: AppConfig):
        self.sheets_gateway = sheets_gateway
        self.config = config

    def fetch_portfolio_rows(self, spreadsheet_id: str) -> PortfolioFetchResult:
        try:
            raw_data = self.sheets_gateway.get_sheet_records(
                spreadsheet_id, 
                self.config.portfolio_range
            )
            
            rows: List[PortfolioRow] = []
            short_rows: List[ShortRow] = []
            # Range is "Portfolio!A2:D", so raw_data[0] is sheet row 2.
            for i, row in enumerate(raw_data):
                sheet_row = i + 2
                # Skip header if it exists (defensive; range normally excludes it).
                if row and str(row[0]).lower() == "symbol":
                    continue
                if len(row) < 4:
                    # Blank rows (0 columns) are skipped; partial rows are flagged.
                    if len(row) > 0:
                        short_rows.append(
                            ShortRow(row_number=sheet_row, column_count=len(row))
                        )
                    continue
                    
                rows.append(PortfolioRow(
                    symbol=str(row[0]).strip(),
                    avg_cost=str(row[1]).strip(),
                    shares=str(row[2]).strip(),
                    current_price=str(row[3]).strip()
                ))
            return PortfolioFetchResult(rows=rows, short_rows=short_rows)
        except Exception as e:
            logger.error(
                "Failed to fetch portfolio rows: %s",
                type(e).__name__,
                extra={"spreadsheet_id": mask_id(spreadsheet_id)},
                exc_info=True,
            )
            raise PortfolioReadError("Error reading portfolio data") from e
