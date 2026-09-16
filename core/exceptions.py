class SheetsReadError(Exception):
    """Raised when a Sheets read fails at a service boundary."""
    pass

class SheetNotFoundError(Exception):
    """Raised when a requested worksheet (tab) does not exist in the spreadsheet."""
    pass

class PortfolioReadError(Exception):
    """Raised when the repository cannot read data from the external source."""
    pass

class PortfolioParseError(Exception):
    """Raised when there is an error parsing row data into models."""
    pass
