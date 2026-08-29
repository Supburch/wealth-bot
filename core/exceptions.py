class SheetsReadError(Exception):
    """Raised when a Sheets read fails at a service boundary."""
    pass

class PortfolioReadError(Exception):
    """Raised when the repository cannot read data from the external source."""
    pass

class PortfolioParseError(Exception):
    """Raised when there is an error parsing row data into models."""
    pass
