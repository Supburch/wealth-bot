"""Tests for config.Settings validation (P2 secrets hardening)."""

import pytest
from pydantic import ValidationError

from config import Settings

VALID_CREDENTIALS = (
    '{"type":"service_account","project_id":"test","private_key":"test-key",'
    '"client_email":"test@example.com"}'
)


def _make_settings(**overrides) -> Settings:
    defaults = {
        "LINE_CHANNEL_SECRET": "secret",
        "LINE_CHANNEL_ACCESS_TOKEN": "token",
        "GOOGLE_CREDENTIALS_JSON": VALID_CREDENTIALS,
        "MASTER_SPREADSHEET_ID": "master-sheet",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_settings_accepts_valid_values():
    settings = _make_settings()
    assert settings.LINE_CHANNEL_SECRET == "secret"
    assert settings.MASTER_SPREADSHEET_ID == "master-sheet"


def test_settings_rejects_empty_line_secret():
    with pytest.raises(ValidationError):
        _make_settings(LINE_CHANNEL_SECRET="")


def test_settings_rejects_empty_line_access_token():
    with pytest.raises(ValidationError):
        _make_settings(LINE_CHANNEL_ACCESS_TOKEN="")


def test_settings_rejects_empty_google_credentials():
    with pytest.raises(ValidationError):
        _make_settings(GOOGLE_CREDENTIALS_JSON="")


def test_settings_rejects_invalid_google_credentials_json():
    with pytest.raises(ValidationError):
        _make_settings(GOOGLE_CREDENTIALS_JSON="not-json")


def test_settings_rejects_non_service_account_credentials():
    with pytest.raises(ValidationError):
        _make_settings(GOOGLE_CREDENTIALS_JSON='{"type":"authorized_user"}')


def test_settings_rejects_service_account_without_private_key():
    with pytest.raises(ValidationError):
        _make_settings(GOOGLE_CREDENTIALS_JSON='{"type":"service_account"}')


def test_master_spreadsheet_id_falls_back_to_spreadsheet_id():
    settings = _make_settings(MASTER_SPREADSHEET_ID="", SPREADSHEET_ID="fallback")
    assert settings.MASTER_SPREADSHEET_ID == "fallback"
