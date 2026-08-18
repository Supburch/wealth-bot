import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Sequence

import gspread
import requests
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials

from config import settings
from core.redaction import mask_id

logger = logging.getLogger(__name__)

_client: gspread.Client | None = None

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Per-HTTP-request timeout (connect + read). gspread's HTTPClient passes
# `timeout=None` (wait forever) to requests by default; this bounds every call.
# Reads are further bounded per logical call by cache.FETCH_TIMEOUT.
HTTP_TIMEOUT = 10.0


def _get_client() -> gspread.Client:
    global _client
    if _client is None:
        creds_dict = json.loads(settings.GOOGLE_CREDENTIALS_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        _client = gspread.authorize(creds)
        _client.http_client.timeout = HTTP_TIMEOUT
        logger.info("Google Sheets client initialized")
    return _client


def invalidate_client():
    global _client
    _client = None
    logger.info("Google Sheets client invalidated")


# ── Read retry (get_sheet_as_dict) ─────────────────────────────────────────────
# Lives INSIDE cache.FETCH_TIMEOUT (7s): 2 attempts × 2.5s + 0.5s backoff = 5.5s
# worst case, leaving ~1.5s margin. Only transient failures are retried.

READ_MAX_ATTEMPTS = 2
READ_ATTEMPT_TIMEOUT = 2.5  # seconds per attempt
READ_BACKOFF_SECONDS = 0.5  # fixed backoff between attempts

_TRANSIENT_NETWORK_ERRORS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
)


def _is_transient_read_error(exc: Exception) -> bool:
    """True for retry-worthy failures: network timeouts/connection errors and
    gspread 5xx responses. Auth (401/403), 4xx, and malformed-data errors are
    NOT retried."""
    if isinstance(exc, _TRANSIENT_NETWORK_ERRORS):
        return True
    if isinstance(exc, APIError):
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        return status is not None and 500 <= status < 600
    return False


def _run_with_timeout(op: Callable[[], Any], timeout: float) -> Any:
    """Run a blocking read in a worker thread with a hard wall-clock timeout."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        return executor.submit(op).result(timeout=timeout)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def get_sheet_as_dict(spreadsheet_id: str, sheet_title: str) -> dict[str, str]:
    """อ่าน Sheet แบบ Metric|Value แล้วคืนเป็น dict"""
    client = _get_client()
    mask = mask_id(spreadsheet_id)

    def _read() -> dict[str, str]:
        sh = client.open_by_key(spreadsheet_id)
        ws = sh.worksheet(sheet_title)
        rows = ws.get_all_values()
        return {row[0]: row[1] for row in rows[1:] if len(row) >= 2}

    last_exc: Exception | None = None
    failure = "unknown"
    for attempt in range(1, READ_MAX_ATTEMPTS + 1):
        try:
            return _run_with_timeout(_read, READ_ATTEMPT_TIMEOUT)
        except TimeoutError as exc:
            last_exc = exc
            failure = "timeout"
        except Exception as exc:
            last_exc = exc
            if not _is_transient_read_error(exc):
                raise
            failure = type(exc).__name__

        if attempt == READ_MAX_ATTEMPTS:
            logger.error(
                "Sheets read failed after %d attempts for %s: %s",
                attempt,
                mask,
                failure,
            )
            raise last_exc

        logger.warning(
            "Sheets read transient failure (attempt %d/%d) for %s: %s",
            attempt,
            READ_MAX_ATTEMPTS,
            mask,
            failure,
        )
        time.sleep(READ_BACKOFF_SECONDS)


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
        await asyncio.to_thread(client.open_by_key, settings.MASTER_SPREADSHEET_ID)
        return True
    except Exception as e:
        logger.error(
            "Google Sheets health check failed: %s",
            type(e).__name__,
            exc_info=True,
        )
        return False
