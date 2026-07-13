import json
import logging
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


def get_sheet_as_dict(sheet_title: str) -> dict[str, str]:
    """อ่าน Sheet แบบ Metric|Value แล้วคืนเป็น dict"""
    client = _get_client()
    sh = client.open_by_key(settings.SPREADSHEET_ID)
    ws = sh.worksheet(sheet_title)
    rows = ws.get_all_values()
    return {row[0]: row[1] for row in rows[1:] if len(row) >= 2}


def get_sheet_records(sheet_title: str) -> list[dict]:
    """อ่าน Sheet แบบมี Header Row แล้วคืนเป็น list of dict"""
    client = _get_client()
    sh = client.open_by_key(settings.SPREADSHEET_ID)
    ws = sh.worksheet(sheet_title)
    return ws.get_all_records()


async def check_sheets_health() -> bool:
    try:
        client = _get_client()
        client.open_by_key(settings.SPREADSHEET_ID)
        return True
    except Exception as e:
        logger.error(f"Google Sheets health check failed: {e}")
        return False
