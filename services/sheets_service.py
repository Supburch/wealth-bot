import json
import logging
from typing import Sequence
import gspread
from google.oauth2.service_account import Credentials
from config import settings

logger = logging.getLogger(__name__)

_client: gspread.Client | None = None

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_client() -> gspread.Client:
    global _client
    if _client is None:
        creds_dict = json.loads(settings.GOOGLE_CREDENTIALS_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        _client = gspread.authorize(creds)
        logger.info("Google Sheets client initialized")
    return _client


def invalidate_client():
    global _client
    _client = None
    logger.info("Google Sheets client invalidated")


def get_sheet_as_dict(spreadsheet_id: str, sheet_title: str) -> dict[str, str]:
    """อ่าน Sheet แบบ Metric|Value แล้วคืนเป็น dict"""
    client = _get_client()
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(sheet_title)
    rows = ws.get_all_values()
    return {row[0]: row[1] for row in rows[1:] if len(row) >= 2}


def get_sheet_records(spreadsheet_id: str, sheet_title: str) -> list[dict]:
    """อ่าน Sheet แบบมี Header Row แล้วคืนเป็น list of dict"""
    client = _get_client()
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(sheet_title)
    return ws.get_all_records()


def get_master_sheet_records(sheet_title: str) -> list[dict]:
    """อ่าน Sheet แบบมี Header Row จาก Master Spreadsheet"""
    client = _get_client()
    sh = client.open_by_key(settings.MASTER_SPREADSHEET_ID)
    ws = sh.worksheet(sheet_title)
    return ws.get_all_records()


def get_raw_range(spreadsheet_id: str, a1_range: str) -> list[list[str]]:
    """
    Read raw cell values using A1 notation (e.g. 'Portfolio!A2:D').
    Returns a 2-D list of strings with no header processing.
    Used by PortfolioRepository via the SheetsGateway adapter in build_router().
    """
    client = _get_client()
    sh = client.open_by_key(spreadsheet_id)
    if "!" in a1_range:
        sheet_title, cell_range = a1_range.split("!", 1)
        ws = sh.worksheet(sheet_title)
        return ws.get(cell_range)
    ws = sh.worksheet(a1_range)
    return ws.get_all_values()


def batch_update_values(
    spreadsheet_id: str,
    sheet_title: str,
    rows: Sequence[Sequence[str | int]],
) -> None:
    """Replace a result sheet with the supplied rows using one batch update."""
    client = _get_client()
    sh = client.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(sheet_title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_title, rows=max(len(rows), 1), cols=9)

    row_count = max(len(rows), 1)
    col_count = max((len(row) for row in rows), default=1)
    if ws.row_count < row_count or ws.col_count < col_count:
        ws.resize(rows=max(ws.row_count, row_count), cols=max(ws.col_count, col_count))

    ws.clear()
    if rows:
        ws.batch_update(
            [{"range": "A1", "values": [list(row) for row in rows]}],
            value_input_option="RAW",
        )


async def check_sheets_health() -> bool:
    try:
        client = _get_client()
        client.open_by_key(settings.MASTER_SPREADSHEET_ID)
        return True
    except Exception as e:
        logger.error(f"Google Sheets health check failed: {e}")
        return False
