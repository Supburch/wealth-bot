import logging
from dataclasses import dataclass
from typing import Protocol, List
from core.sheet_config import AppConfig
from core.exceptions import PortfolioReadError, SheetNotFoundError
from core.redaction import mask_id
from models.portfolio import DrCostRow, PortfolioRow

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


# Column indices (0-based) for the 'from Streaming-DR' main table (range A2:N200).
_DR_SYMBOL_COL = 2    # C — symbol
_DR_TYPE_COL = 11     # L — type marker ("DR")


def _is_blank_row(row: List[str]) -> bool:
    return all(not str(cell).strip() for cell in row)


def _normalize_dr_symbol(symbol: str) -> str:
    """Normalize a DR symbol for matching: strip '.BK' suffix, uppercase."""
    s = symbol.strip().upper()
    if s.endswith(".BK"):
        s = s[:-3]
    return s


def _is_positive_number(value: str) -> bool:
    """True when ``value`` parses to a positive number after currency cleanup."""
    cleaned = value.replace(",", "").replace("฿", "").replace("$", "").replace("%", "").strip()
    if not cleaned:
        return False
    try:
        return float(cleaned) > 0
    except ValueError:
        return False


def _is_error_cell(value: str) -> bool:
    """True when ``value`` is a spreadsheet error placeholder (#N/A, #DIV/0!)."""
    s = value.strip().upper()
    return s.startswith("#") or s == "N/A"


# Column indices (0-based) for the DR cost table (range A201:G233, section 1).
_DR_COST_AVG_COL = 0      # A — avg cost per share
_DR_COST_VOLUME_COL = 1   # B — volume (shares)
_DR_COST_PCT_COL = 3      # D — % P/L (error rows are filtered out)
_DR_COST_SYMBOL_COL = 4   # E — symbol
_DR_COST_PRICE_COL = 5    # F — current price per share


@dataclass
class DrCostFetchResult:
    """Valid DR cost-table rows (held DRs with a complete, consistent cost basis)."""
    rows: List[DrCostRow]


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

    def fetch_dr_holdings(self, spreadsheet_id: str) -> List[str]:
        """Return the DR position symbols (type marker "DR") from the main table.

        The ⚠ flag and market-value columns are deliberately ignored: the flag is
        a false positive caused by a broken VLOOKUP, and market value is read from
        the cost table instead. Symbols are normalized ('.BK' stripped, uppercased).
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
            return []
        except Exception as e:
            logger.error(
                "Failed to fetch DR holdings: %s",
                type(e).__name__,
                extra={"spreadsheet_id": mask_id(spreadsheet_id)},
                exc_info=True,
            )
            raise PortfolioReadError("Error reading DR holdings") from e

        symbols: List[str] = []
        for row in raw_data:
            if not row or _is_blank_row(row):
                continue
            type_marker = str(row[_DR_TYPE_COL]).strip() if len(row) > _DR_TYPE_COL else ""
            if type_marker != "DR":
                continue
            symbol = str(row[_DR_SYMBOL_COL]).strip() if len(row) > _DR_SYMBOL_COL else ""
            normalized = _normalize_dr_symbol(symbol)
            if normalized:
                symbols.append(normalized)
        return symbols

    def fetch_dr_cost_rows(self, spreadsheet_id: str) -> DrCostFetchResult:
        """Read the DR cost table (section 1) and return its valid rows.

        A row is valid when it has a non-empty symbol, a positive avg cost and
        volume, and a % P/L cell that is not a spreadsheet error placeholder.
        Error/empty rows correspond to watchlist or incomplete DRs without a
        reliable cost basis and are skipped.
        """
        try:
            raw_data = self.sheets_gateway.get_sheet_records(
                spreadsheet_id, self.config.dr_cost_range
            )
        except SheetNotFoundError:
            logger.info(
                "DR cost table missing; no DR cost basis available",
                extra={"spreadsheet_id": mask_id(spreadsheet_id)},
            )
            return DrCostFetchResult(rows=[])
        except Exception as e:
            logger.error(
                "Failed to fetch DR cost rows: %s",
                type(e).__name__,
                extra={"spreadsheet_id": mask_id(spreadsheet_id)},
                exc_info=True,
            )
            raise PortfolioReadError("Error reading DR cost table") from e

        rows: List[DrCostRow] = []
        for row in raw_data:
            if not row or _is_blank_row(row):
                continue
            symbol = str(row[_DR_COST_SYMBOL_COL]).strip() if len(row) > _DR_COST_SYMBOL_COL else ""
            symbol = _normalize_dr_symbol(symbol)
            if not symbol:
                continue
            avg_cost = str(row[_DR_COST_AVG_COL]).strip() if len(row) > _DR_COST_AVG_COL else ""
            volume = str(row[_DR_COST_VOLUME_COL]).strip() if len(row) > _DR_COST_VOLUME_COL else ""
            pct_pl = str(row[_DR_COST_PCT_COL]).strip() if len(row) > _DR_COST_PCT_COL else ""
            current_price = str(row[_DR_COST_PRICE_COL]).strip() if len(row) > _DR_COST_PRICE_COL else ""
            if not _is_positive_number(avg_cost) or not _is_positive_number(volume):
                continue
            if _is_error_cell(pct_pl):
                continue
            rows.append(DrCostRow(
                symbol=symbol,
                avg_cost=avg_cost,
                volume=volume,
                current_price=current_price,
            ))
        return DrCostFetchResult(rows=rows)
