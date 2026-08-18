"""
test_sheets_service.py — Unit tests for services/sheets_service.py

P3.1b: verifies the gspread client-level HTTP timeout is actually applied.
No network calls — gspread authorize and the credentials loader are mocked.
"""
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

import services.sheets_service as ss
from gspread.exceptions import APIError


def test_get_client_sets_http_timeout(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(ss, "_client", None)  # force re-init on next call
    monkeypatch.setattr(ss, "settings", SimpleNamespace(GOOGLE_CREDENTIALS_JSON="{}"))
    monkeypatch.setattr(ss, "Credentials", MagicMock())
    monkeypatch.setattr(ss.gspread, "authorize", lambda creds: fake_client)

    client = ss._get_client()

    assert client is fake_client
    assert ss.HTTP_TIMEOUT == 10.0
    assert client.http_client.timeout == ss.HTTP_TIMEOUT


# ── get_sheet_as_dict retry (P3.1d) ──────────────────────────────────────────


def _api_error(status_code: int) -> APIError:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = {"error": {"code": status_code, "message": "err", "status": "ERR"}}
    return APIError(response)


@pytest.mark.parametrize(
    "exc, expected",
    [
        (requests.exceptions.Timeout("t"), True),
        (requests.exceptions.ConnectionError("c"), True),
        (_api_error(500), True),
        (_api_error(502), True),
        (_api_error(503), True),
        (_api_error(401), False),
        (_api_error(403), False),
        (_api_error(404), False),
        (ValueError("malformed"), False),
    ],
)
def test_is_transient_read_error(exc, expected):
    assert ss._is_transient_read_error(exc) is expected


def test_get_sheet_as_dict_retries_transient_then_succeeds():
    fake_ws = MagicMock()
    fake_ws.get_all_values.return_value = [["Metric", "Value"], ["A", "1"]]
    fake_sh = MagicMock()
    fake_sh.worksheet.return_value = fake_ws

    fake_client = MagicMock()
    fake_client.open_by_key.side_effect = [
        requests.exceptions.ConnectionError("boom"),
        fake_sh,
    ]

    with patch.object(ss, "_get_client", return_value=fake_client), patch(
        "services.sheets_service.time.sleep"
    ) as mock_sleep:
        result = ss.get_sheet_as_dict("sheet-123", "TodaySummary")

    assert result == {"A": "1"}
    assert fake_client.open_by_key.call_count == 2
    mock_sleep.assert_called_once_with(ss.READ_BACKOFF_SECONDS)


def test_get_sheet_as_dict_does_not_retry_non_transient():
    fake_client = MagicMock()
    fake_client.open_by_key.side_effect = _api_error(401)

    with patch.object(ss, "_get_client", return_value=fake_client), patch(
        "services.sheets_service.time.sleep"
    ) as mock_sleep, pytest.raises(APIError):
        ss.get_sheet_as_dict("sheet-123", "TodaySummary")

    assert fake_client.open_by_key.call_count == 1
    mock_sleep.assert_not_called()


def test_get_sheet_as_dict_raises_after_max_attempts():
    fake_client = MagicMock()
    fake_client.open_by_key.side_effect = requests.exceptions.ConnectionError("boom")

    with patch.object(ss, "_get_client", return_value=fake_client), patch(
        "services.sheets_service.time.sleep"
    ) as mock_sleep, pytest.raises(requests.exceptions.ConnectionError):
        ss.get_sheet_as_dict("sheet-123", "TodaySummary")

    assert fake_client.open_by_key.call_count == ss.READ_MAX_ATTEMPTS
    assert mock_sleep.call_count == ss.READ_MAX_ATTEMPTS - 1


def test_get_sheet_as_dict_retries_on_timeout():
    with patch.object(ss, "_get_client", return_value=MagicMock()), patch.object(
        ss, "_run_with_timeout", side_effect=[TimeoutError(), {"A": "1"}]
    ), patch("services.sheets_service.time.sleep") as mock_sleep:
        result = ss.get_sheet_as_dict("sheet-123", "TodaySummary")

    assert result == {"A": "1"}
    mock_sleep.assert_called_once_with(ss.READ_BACKOFF_SECONDS)


def test_get_sheet_as_dict_logs_masked_id_not_plaintext(caplog):
    raw_id = "spreadsheet-123"
    fake_client = MagicMock()
    fake_client.open_by_key.side_effect = requests.exceptions.ConnectionError("boom")

    with patch.object(ss, "_get_client", return_value=fake_client), patch(
        "services.sheets_service.time.sleep"
    ):
        with caplog.at_level(logging.WARNING, logger="services.sheets_service"):
            with pytest.raises(requests.exceptions.ConnectionError):
                ss.get_sheet_as_dict(raw_id, "TodaySummary")

    assert raw_id not in caplog.text
    assert ss.mask_id(raw_id) in caplog.text
