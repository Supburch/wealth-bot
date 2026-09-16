import logging
from dataclasses import dataclass
from typing import Protocol, List
from core.sheet_config import AppConfig
from core.exceptions import PortfolioReadError, SheetNotFoundError
from core.redaction import mask_id
from models.portfolio import DrHolding, PortfolioRow

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


# Column indices (0-based) for the 'from Streaming-DR' sheet (range A2:N200).
_DR_SYMBOL_COL = 0   # A — symbol
_DR_TYPE_COL = 11    # L — type marker ("DR")
_DR_VALUE_COL = 12   # M — THB market value (already THB, no FX conversion)
_DR_FLAG_COL = 13    # N — pending-review flag ("⚠ …")
_DR_FLAG_PREFIX = "⚠"


def _is_blank_row(row: List[str]) -> bool:
    return all(not str(cell).strip() for cell in row)


@dataclass
class DrFetchResult:
    """Parsed DR holdings plus a count of pending-review (⚠) rows."""
    holdings: List[DrHolding]
    skipped_count: int


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

    def fetch_dr_holdings(self, spreadsheet_id: str) -> DrFetchResult:
        """Read DR positions from the 'from Streaming-DR' sheet.

        Only rows whose type marker (column L) equals "DR" are returned. Rows
        whose flag column (N) starts with "⚠" are pending review and are counted
        in ``skipped_count`` rather than included in ``holdings`` (so they never
        contribute to totals). Blank rows and non-DR rows are ignored.
        """
        try:
            raw_data = self.sheets_gateway.get_sheet_records(
                spreadsheet_id, self.config.dr_range
            )
        except SheetNotFoundError:
            # The 'from Streaming-DR' sheet does not exist for this user. Degrade
            # gracefully to a US-only portfolio instead of failing the command.
            logger.info(
                "DR sheet missing; degrading to US-only portfolio",
                extra={"spreadsheet_id": mask_id(spreadsheet_id)},
            )
            return DrFetchResult(holdings=[], skipped_count=0)
        except Exception as e:
            logger.error(
                "Failed to fetch DR holdings: %s",
                type(e).__name__,
                extra={"spreadsheet_id": mask_id(spreadsheet_id)},
                exc_info=True,
            )
            raise PortfolioReadError("Error reading DR holdings") from e

        holdings: List[DrHolding] = []
        skipped_count = 0
        for row in raw_data:
            if not row or _is_blank_row(row):
                continue
            type_marker = str(row[_DR_TYPE_COL]).strip() if len(row) > _DR_TYPE_COL else ""
            if type_marker != "DR":
                continue
            flag = str(row[_DR_FLAG_COL]).strip() if len(row) > _DR_FLAG_COL else ""
            if flag.startswith(_DR_FLAG_PREFIX):
                skipped_count += 1
                continue
            symbol = str(row[_DR_SYMBOL_COL]).strip() if len(row) > _DR_SYMBOL_COL else ""
            value = str(row[_DR_VALUE_COL]).strip() if len(row) > _DR_VALUE_COL else ""
            holdings.append(DrHolding(symbol=symbol, value_thb=value))
        return DrFetchResult(holdings=holdings, skipped_count=skipped_count)
