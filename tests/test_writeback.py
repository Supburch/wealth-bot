"""
test_writeback.py — Retry/error semantics, idempotency, and async writeback tests.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.validation import ValidationIssue, ValidationSummary
from services.cache import check_and_set_idempotency, clear_cache, clear_idempotency
from services.writeback_service import WriteBackService


def _sample_summary(**overrides) -> ValidationSummary:
    defaults = dict(total_rows=2, valid_rows=2, invalid_rows=0, issues=[])
    defaults.update(overrides)
    return ValidationSummary(**defaults)


@pytest.fixture(autouse=True)
async def reset_cache():
    await clear_cache()
    yield
    await clear_cache()


# ── Deterministic idempotency key ────────────────────────────────────────────


def test_idempotency_key_is_deterministic_for_identical_summaries():
    service = WriteBackService(MagicMock())
    summary_a = _sample_summary()
    summary_b = _sample_summary()

    key_a = service._generate_idempotency_key("sheet_1", summary_a)
    key_b = service._generate_idempotency_key("sheet_1", summary_b)

    assert key_a == key_b
    assert key_a.startswith("writeback:sheet_1:")


def test_idempotency_key_differs_by_spreadsheet():
    service = WriteBackService(MagicMock())
    summary = _sample_summary()

    key_a = service._generate_idempotency_key("sheet_a", summary)
    key_b = service._generate_idempotency_key("sheet_b", summary)

    assert key_a != key_b


def test_idempotency_key_differs_by_summary_content():
    service = WriteBackService(MagicMock())
    base = _sample_summary()
    changed = _sample_summary(
        invalid_rows=1,
        valid_rows=1,
        issues=[ValidationIssue(row_index=2, symbol="X", error_message="bad")],
    )

    assert service._generate_idempotency_key("sheet_1", base) != service._generate_idempotency_key(
        "sheet_1", changed
    )


# ── Idempotency cache semantics ──────────────────────────────────────────────


async def test_check_and_set_idempotency_first_call_is_not_duplicate():
    assert await check_and_set_idempotency("wb:test") is False


async def test_check_and_set_idempotency_second_call_is_duplicate():
    assert await check_and_set_idempotency("wb:test") is False
    assert await check_and_set_idempotency("wb:test") is True


async def test_clear_idempotency_allows_retry_after_failure():
    key = "wb:retry"
    assert await check_and_set_idempotency(key) is False
    assert await check_and_set_idempotency(key) is True

    await clear_idempotency(key)
    assert await check_and_set_idempotency(key) is False


# ── Retry / error semantics ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_writeback_skips_duplicate_via_idempotency():
    repo = MagicMock()
    service = WriteBackService(repo)
    summary = _sample_summary()

    with patch(
        "services.writeback_service.check_and_set_idempotency",
        AsyncMock(return_value=True),
    ):
        result = await service.write_validation_result("sheet_1", summary)

    assert result is None
    repo.save_result.assert_not_called()


@pytest.mark.asyncio
async def test_writeback_retries_transient_failures_then_succeeds():
    repo = MagicMock()
    repo.save_result.side_effect = [ConnectionError("transient"), ConnectionError("transient"), None]
    service = WriteBackService(repo)
    summary = _sample_summary()

    with (
        patch("services.writeback_service.check_and_set_idempotency", AsyncMock(return_value=False)),
        patch("services.writeback_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        result = await service.write_validation_result("sheet_1", summary)

    assert result is not None
    assert result.spreadsheet_id == "sheet_1"
    assert repo.save_result.call_count == 3
    mock_sleep.assert_any_call(1)
    mock_sleep.assert_any_call(2)


@pytest.mark.asyncio
async def test_writeback_raises_after_max_retries():
    repo = MagicMock()
    repo.save_result.side_effect = RuntimeError("persistent failure")
    service = WriteBackService(repo)
    summary = _sample_summary()

    with (
        patch("services.writeback_service.check_and_set_idempotency", AsyncMock(return_value=False)),
        patch("services.writeback_service.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(RuntimeError, match="persistent failure"),
    ):
        await service.write_validation_result("sheet_1", summary)

    assert repo.save_result.call_count == 3


@pytest.mark.asyncio
async def test_writeback_clears_idempotency_key_after_final_failure():
    repo = MagicMock()
    repo.save_result.side_effect = OSError("disk full")
    service = WriteBackService(repo)
    summary = _sample_summary()
    key = service._generate_idempotency_key("sheet_1", summary)

    with (
        patch("services.writeback_service.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(OSError),
    ):
        await service.write_validation_result("sheet_1", summary)

    assert await check_and_set_idempotency(key) is False


@pytest.mark.asyncio
async def test_writeback_retries_on_timeout():
    repo = MagicMock()
    service = WriteBackService(repo)
    summary = _sample_summary()

    wait_for_results = [TimeoutError(), None]

    async def fake_wait_for(coro, *, timeout):
        result = wait_for_results.pop(0)
        if isinstance(result, BaseException):
            coro.close()
            raise result
        return await coro

    with (
        patch("services.writeback_service.check_and_set_idempotency", AsyncMock(return_value=False)),
        patch("services.writeback_service.asyncio.wait_for", side_effect=fake_wait_for),
        patch("services.writeback_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        result = await service.write_validation_result("sheet_1", summary)

    assert result is not None
    repo.save_result.assert_called_once()
    mock_sleep.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_writeback_delegates_sync_save_to_thread():
    repo = MagicMock()
    service = WriteBackService(repo)
    summary = _sample_summary()

    with (
        patch("services.writeback_service.check_and_set_idempotency", AsyncMock(return_value=False)),
        patch("services.writeback_service.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread,
    ):
        mock_to_thread.return_value = None
        await service.write_validation_result("sheet_1", summary)

    mock_to_thread.assert_awaited_once()
    assert mock_to_thread.await_args.args[0] is repo.save_result
