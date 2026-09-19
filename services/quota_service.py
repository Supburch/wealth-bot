"""Quota service — polls the LINE Messaging API for monthly message usage.

The LINE free plan enforces a monthly message quota; when usage approaches the
limit the bot silently stops replying. This service wraps the SDK quota
endpoints and exposes a single ``QuotaStatus`` snapshot so callers can warn
before that happens.

SDK contract (line-bot-sdk v3):
- ``MessagingApi.get_message_quota_consumption()`` → ``QuotaConsumptionResponse``
  with ``total_usage`` (int, messages sent this month).
- ``MessagingApi.get_message_quota()`` → ``MessageQuotaResponse`` with
  ``type`` (QuotaType.NONE = unlimited / LIMITED) and ``value`` (the monthly
  limit, present only when LIMITED).
"""
import asyncio
import logging

from linebot.v3.messaging import QuotaType

from models.quota import QuotaStatus

logger = logging.getLogger(__name__)

# Warn when remaining messages drop below this absolute count.
LOW_QUOTA_THRESHOLD = 100


class QuotaService:
    """Computes the current LINE message-quota status.

    ``messaging_api`` is any object exposing the two SDK quota methods; tests
    inject a fake. The low-quota threshold (an absolute remaining-message
    count) is injectable for tests.
    """

    def __init__(self, messaging_api, low_threshold: int = LOW_QUOTA_THRESHOLD):
        self._api = messaging_api
        self._threshold = low_threshold

    async def get_status(self) -> QuotaStatus:
        # The SDK quota methods are synchronous HTTP calls; run them off the
        # event loop so the webhook is never blocked on network I/O.
        usage_resp = await asyncio.to_thread(self._api.get_message_quota_consumption)
        quota_resp = await asyncio.to_thread(self._api.get_message_quota)

        total_usage = int(usage_resp.total_usage)

        if quota_resp.type == QuotaType.NONE or quota_resp.value is None:
            return QuotaStatus(
                total_usage=total_usage,
                quota_limit=None,
                remaining=None,
                usage_percent=None,
                is_low=False,
            )

        quota_limit = int(quota_resp.value)
        remaining = max(quota_limit - total_usage, 0)
        usage_percent = round(total_usage / quota_limit * 100, 2) if quota_limit > 0 else 100.0

        is_low = quota_limit > 0 and remaining < self._threshold

        return QuotaStatus(
            total_usage=total_usage,
            quota_limit=quota_limit,
            remaining=remaining,
            usage_percent=usage_percent,
            is_low=is_low,
        )
