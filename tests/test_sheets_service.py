"""
test_sheets_service.py — Unit tests for services/sheets_service.py

P3.1b: verifies the gspread client-level HTTP timeout is actually applied.
No network calls — gspread authorize and the credentials loader are mocked.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_get_client_sets_http_timeout(monkeypatch):
    import services.sheets_service as ss

    fake_client = MagicMock()
    monkeypatch.setattr(ss, "_client", None)  # force re-init on next call
    monkeypatch.setattr(ss, "settings", SimpleNamespace(GOOGLE_CREDENTIALS_JSON="{}"))
    monkeypatch.setattr(ss, "Credentials", MagicMock())
    monkeypatch.setattr(ss.gspread, "authorize", lambda creds: fake_client)

    client = ss._get_client()

    assert client is fake_client
    assert ss.HTTP_TIMEOUT == 10.0
    assert client.http_client.timeout == ss.HTTP_TIMEOUT
