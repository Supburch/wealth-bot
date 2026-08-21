"""
test_correlation.py — Per-request correlation ID (P2.5c).

Verifies the contextvars-based correlation ID: every log record emitted during
a request carries the same ID, including records written inside
``asyncio.to_thread``, while concurrent requests get distinct IDs.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging

from fastapi.testclient import TestClient
from unittest.mock import patch

import main
from config import settings
from core.correlation import RequestIdFilter, request_id_var
from models.response import AppResponse


class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _capture(name="test.correlation"):
    handler = _CaptureHandler()
    handler.addFilter(RequestIdFilter())
    logger = logging.getLogger(name)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger, handler


def test_filter_stamps_default_when_unset():
    logger, handler = _capture()
    logger.info("outside any request")
    assert [r.request_id for r in handler.records] == ["-"]


def test_request_id_propagates_through_to_thread():
    logger, handler = _capture()

    async def run():
        token = request_id_var.set("req-1")
        try:
            logger.info("before thread")

            def log_in_thread():
                logging.getLogger("test.correlation").info("in thread")

            await asyncio.to_thread(log_in_thread)
            logger.info("after thread")
        finally:
            request_id_var.reset(token)

    asyncio.run(run())
    assert [r.request_id for r in handler.records] == ["req-1", "req-1", "req-1"]


def test_concurrent_requests_get_distinct_ids():
    logger, handler = _capture()

    async def worker(rid):
        token = request_id_var.set(rid)
        try:
            def log_in_thread():
                logging.getLogger("test.correlation").info("work")

            await asyncio.to_thread(log_in_thread)
        finally:
            request_id_var.reset(token)

    async def run():
        await asyncio.gather(worker("req-A"), worker("req-B"))

    asyncio.run(run())
    assert len(handler.records) == 2
    assert {r.request_id for r in handler.records} == {"req-A", "req-B"}


def _sign(body: str) -> str:
    digest = hmac.new(
        settings.LINE_CHANNEL_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode()


def _message_body() -> str:
    return json.dumps({
        "destination": "U00000000000000000000000000000000",
        "events": [{
            "type": "message",
            "webhookEventId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "deliveryContext": {"isRedelivery": False},
            "timestamp": 1700000000000,
            "source": {"type": "user", "userId": "U123"},
            "replyToken": "reply-token",
            "mode": "active",
            "message": {
                "type": "text",
                "id": "message-id",
                "quoteToken": "quote-token",
                "text": "portfolio",
            },
        }],
    })


def test_webhook_request_logs_share_one_id():
    handler = _CaptureHandler()
    handler.addFilter(RequestIdFilter())
    main.logger.addHandler(handler)
    original_level = main.logger.level
    main.logger.setLevel(logging.DEBUG)
    try:
        async def fake_route(user_id, raw_command):
            logging.getLogger("main").info("routing %s", raw_command)

            def sheet_read():
                logging.getLogger("main").info("reading sheet in thread")

            await asyncio.to_thread(sheet_read)
            return AppResponse(text="ok")

        body = _message_body()
        with patch.object(main.router, "route_command", fake_route), \
                patch("main.ApiClient"), patch("main.MessagingApi"):
            with TestClient(main.app) as c:
                resp = c.post(
                    "/callback",
                    content=body,
                    headers={"X-Line-Signature": _sign(body)},
                )

        assert resp.status_code == 200
    finally:
        main.logger.removeHandler(handler)
        main.logger.setLevel(original_level)

    request_records = [r for r in handler.records if r.request_id != "-"]
    ids = {r.request_id for r in request_records}
    assert len(ids) == 1
    rid = ids.pop()
    assert rid != "-"
    assert any("reading sheet in thread" in r.getMessage() for r in request_records)
