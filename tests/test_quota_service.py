"""Tests for services.quota_service.QuotaService and main quota-warning helpers."""
import pytest
from linebot.v3.messaging import (
    MessageQuotaResponse,
    QuotaConsumptionResponse,
    QuotaType,
)

import main
from core.enums import ResponseType
from models.quota import QuotaStatus
from models.response import AppResponse
from services.quota_service import QuotaService


class FakeMessagingApi:
    def __init__(self, total_usage: int, quota_type: QuotaType, quota_value):
        self._usage = QuotaConsumptionResponse(total_usage=total_usage)
        self._quota = MessageQuotaResponse(type=quota_type, value=quota_value)
        self.calls = 0

    def get_message_quota_consumption(self):
        self.calls += 1
        return self._usage

    def get_message_quota(self):
        return self._quota


class BrokenMessagingApi:
    def get_message_quota_consumption(self):
        raise RuntimeError("boom")

    def get_message_quota(self):
        raise RuntimeError("boom")


# ── QuotaService (absolute threshold) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_quota_status_low_when_remaining_below_threshold():
    api = FakeMessagingApi(950, QuotaType.LIMITED, 1000)
    status = await QuotaService(api, low_threshold=100).get_status()

    assert status.total_usage == 950
    assert status.quota_limit == 1000
    assert status.remaining == 50
    assert status.usage_percent == 95.0
    assert status.is_low is True


@pytest.mark.asyncio
async def test_quota_status_healthy_when_above_threshold():
    api = FakeMessagingApi(500, QuotaType.LIMITED, 1000)
    status = await QuotaService(api, low_threshold=100).get_status()

    assert status.remaining == 500
    assert status.usage_percent == 50.0
    assert status.is_low is False


@pytest.mark.asyncio
async def test_quota_status_unlimited():
    api = FakeMessagingApi(12345, QuotaType.NONE, None)
    status = await QuotaService(api).get_status()

    assert status.total_usage == 12345
    assert status.quota_limit is None
    assert status.remaining is None
    assert status.usage_percent is None
    assert status.is_low is False


@pytest.mark.asyncio
async def test_quota_status_not_low_at_exactly_threshold():
    # remaining == 100 → NOT low (threshold is strictly-less-than).
    api = FakeMessagingApi(900, QuotaType.LIMITED, 1000)
    status = await QuotaService(api, low_threshold=100).get_status()

    assert status.remaining == 100
    assert status.is_low is False


# ── main.get_quota_status ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_quota_status_returns_status_when_low(monkeypatch):
    monkeypatch.setattr(main, "_last_quota_check", 0.0)
    monkeypatch.setattr(main, "_quota_status_cache", None)
    api = FakeMessagingApi(950, QuotaType.LIMITED, 1000)

    status = await main.get_quota_status(api)

    assert status is not None
    assert status.is_low is True
    assert status.remaining == 50


@pytest.mark.asyncio
async def test_get_quota_status_caches_within_interval(monkeypatch):
    monkeypatch.setattr(main, "_last_quota_check", 0.0)
    monkeypatch.setattr(main, "_quota_status_cache", None)
    api = FakeMessagingApi(950, QuotaType.LIMITED, 1000)

    await main.get_quota_status(api)
    assert api.calls == 1

    # Second call within the interval reuses the cache; no new API call.
    await main.get_quota_status(api)
    assert api.calls == 1


@pytest.mark.asyncio
async def test_get_quota_status_swallows_api_errors(monkeypatch):
    monkeypatch.setattr(main, "_last_quota_check", 0.0)
    monkeypatch.setattr(main, "_quota_status_cache", None)

    status = await main.get_quota_status(BrokenMessagingApi())  # must not raise

    assert status is None


# ── main._append_quota_warning ─────────────────────────────────────────────────

def _low_status() -> QuotaStatus:
    return QuotaStatus(
        total_usage=950,
        quota_limit=1000,
        remaining=50,
        usage_percent=95.0,
        is_low=True,
    )


def test_append_quota_warning_to_text_response():
    response = AppResponse(text="พอร์ตของคุณ")
    result = main._append_quota_warning(response, _low_status())

    assert "โควตาข้อความใกล้เต็ม" in result.text
    assert "50/1000" in result.text
    assert result.text.startswith("พอร์ตของคุณ")


def test_append_quota_warning_to_flex_response():
    label = "PORTFOLIO"
    response = AppResponse(
        type=ResponseType.RICH,
        alt_text="portfolio",
        contents={
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [{"type": "text", "text": label}],
            },
        },
    )
    result = main._append_quota_warning(response, _low_status())

    body_contents = result.contents["body"]["contents"]
    assert len(body_contents) == 3  # original + separator + warning
    assert body_contents[0]["text"] == label
    assert body_contents[1]["type"] == "separator"
    assert "โควตาข้อความใกล้เต็ม" in body_contents[2]["text"]
