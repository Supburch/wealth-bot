"""Tests for services/user_mapping_service.py.

Focus: a failed user-mapping fetch must raise (not be swallowed into a cached
``{}``), so the ``@cached`` decorator never negative-caches a transient failure.
"""
import pytest
from unittest.mock import patch, AsyncMock

from services.cache import clear_cache


@pytest.fixture(autouse=True)
async def _clean_cache():
    await clear_cache()
    yield
    await clear_cache()


async def test_fetch_all_users_returns_mapping():
    from services import user_mapping_service as ums
    rows = [
        {"LINE_USER_ID": "U1", "SPREADSHEET_ID": "S1", "ROLE": "user", "ENABLED": "TRUE"},
        {"LINE_USER_ID": "U2", "SPREADSHEET_ID": "S2", "ROLE": "admin", "ENABLED": "FALSE"},
    ]
    with patch("services.user_mapping_service.get_master_sheet_records", return_value=rows):
        result = await ums._fetch_all_users()
    assert set(result) == {"U1", "U2"}
    assert result["U1"].enabled is True
    assert result["U2"].enabled is False
    assert result["U2"].is_admin is True


async def test_fetch_all_users_raises_on_failure():
    from services import user_mapping_service as ums
    with patch(
        "services.user_mapping_service.get_master_sheet_records",
        side_effect=ConnectionError("boom"),
    ):
        with pytest.raises(ConnectionError):
            await ums._fetch_all_users()


async def test_failure_does_not_poison_cache():
    from services import user_mapping_service as ums
    from services.cache import get_cache_entries_count
    with patch(
        "services.user_mapping_service.get_master_sheet_records",
        side_effect=ConnectionError("boom"),
    ):
        with pytest.raises(ConnectionError):
            await ums._fetch_all_users()
    assert get_cache_entries_count() == 0


async def test_failure_is_retried_not_served_from_cache():
    from services import user_mapping_service as ums
    calls = {"n": 0}

    def fake(worksheet):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("boom")
        return [{"LINE_USER_ID": "U1", "SPREADSHEET_ID": "S1", "ROLE": "user", "ENABLED": "TRUE"}]

    with patch("services.user_mapping_service.get_master_sheet_records", side_effect=fake):
        with pytest.raises(ConnectionError):
            await ums._fetch_all_users()
        result = await ums._fetch_all_users()
    assert calls["n"] == 2
    assert "U1" in result


async def test_get_user_returns_mapping():
    from services import user_mapping_service as ums
    rows = [{"LINE_USER_ID": "U1", "SPREADSHEET_ID": "S1", "ROLE": "user", "ENABLED": "TRUE"}]
    with patch("services.user_mapping_service.get_master_sheet_records", return_value=rows):
        result = await ums.get_user("U1")
    assert result is not None
    assert result.spreadsheet_id == "S1"


async def test_get_user_returns_none_for_missing_user():
    from services import user_mapping_service as ums
    with patch(
        "services.user_mapping_service.get_master_sheet_records",
        return_value=[],
    ):
        result = await ums.get_user("U_MISSING")
    assert result is None


async def test_get_user_propagates_fetch_failure():
    from services import user_mapping_service as ums
    with patch(
        "services.user_mapping_service.get_master_sheet_records",
        side_effect=ConnectionError("boom"),
    ):
        with pytest.raises(ConnectionError):
            await ums.get_user("U1")


async def test_handler_returns_unavailable_not_denied_on_fetch_failure():
    from handlers.today_handler import TodayHandler
    from core.messages import UNEXPECTED_ERROR, ACCESS_DENIED
    with patch(
        "handlers.today_handler.get_user",
        AsyncMock(side_effect=ConnectionError("boom")),
    ):
        result = await TodayHandler().handle("U_UNKNOWN")
    assert result.text == UNEXPECTED_ERROR
    assert result.text != ACCESS_DENIED
