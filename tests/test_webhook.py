"""
test_webhook.py — Tests for the LINE webhook `/callback` endpoint (P2 validation).

Covers the signature-validation hardening:
- Missing X-Line-Signature header → 401 (regression: previously 500 via AttributeError)
- Invalid signature → 401
- Empty body → 400
- Valid signature + valid message event → 200 and a reply is sent
"""
import base64
import hashlib
import hmac
import json
import logging

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

import main
from config import settings
from models.response import AppResponse


@pytest.fixture()
def client():
    with TestClient(main.app) as c:
        yield c


def _sign(body: str) -> str:
    """Compute the X-Line-Signature for the given body using the app secret."""
    digest = hmac.new(
        settings.LINE_CHANNEL_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode()


def _message_body() -> str:
    """A valid LINE text-message webhook body (all SDK-required fields present)."""
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


def test_callback_missing_signature_returns_401(client):
    resp = client.post("/callback", content=_message_body())
    assert resp.status_code == 401


def test_callback_invalid_signature_returns_401(client):
    resp = client.post(
        "/callback",
        content=_message_body(),
        headers={"X-Line-Signature": "not-a-valid-signature"},
    )
    assert resp.status_code == 401


def test_callback_empty_body_returns_400(client):
    resp = client.post(
        "/callback",
        content="",
        headers={"X-Line-Signature": _sign("")},
    )
    assert resp.status_code == 400


def test_callback_valid_signature_processes(client):
    body = _message_body()
    with patch.object(
        main.router, "route_command", AsyncMock(return_value=AppResponse(text="ok"))
    ), patch("main.ApiClient"), patch("main.MessagingApi") as mock_messaging_cls:
        mock_api = mock_messaging_cls.return_value
        resp = client.post(
            "/callback",
            content=body,
            headers={"X-Line-Signature": _sign(body)},
        )

    assert resp.status_code == 200
    mock_api.reply_message.assert_called_once()


def test_callback_checks_quota_status(client):
    """The webhook fetches the (throttled) quota status before replying."""
    body = _message_body()
    with patch.object(
        main.router, "route_command", AsyncMock(return_value=AppResponse(text="ok"))
    ), patch("main.ApiClient"), patch("main.MessagingApi"), \
         patch.object(main, "get_quota_status", AsyncMock(return_value=None)) as quota_mock:
        resp = client.post(
            "/callback",
            content=body,
            headers={"X-Line-Signature": _sign(body)},
        )

    assert resp.status_code == 200
    quota_mock.assert_awaited_once()


def test_callback_appends_quota_warning_when_low(client):
    """A low-quota status appends a warning to the reply text."""
    from linebot.v3.messaging import TextMessage
    from models.quota import QuotaStatus

    body = _message_body()
    status = QuotaStatus(
        total_usage=950, quota_limit=1000, remaining=50, usage_percent=95.0, is_low=True
    )
    with patch.object(
        main.router, "route_command", AsyncMock(return_value=AppResponse(text="ok"))
    ), patch("main.ApiClient"), patch("main.MessagingApi") as mock_messaging_cls, \
         patch.object(main, "get_quota_status", AsyncMock(return_value=status)):
        mock_api = mock_messaging_cls.return_value
        resp = client.post(
            "/callback",
            content=body,
            headers={"X-Line-Signature": _sign(body)},
        )

    assert resp.status_code == 200
    request = mock_api.reply_message.call_args.args[0]
    messages = request.messages
    assert len(messages) == 1
    assert isinstance(messages[0], TextMessage)
    assert "โควตาข้อความใกล้เต็ม" in messages[0].text


def test_callback_appends_chart_image_message(client):
    """An AppResponse with image_url sends the text/flex message then an image."""
    from linebot.v3.messaging import ImageMessage

    body = _message_body()
    with patch.object(
        main.router,
        "route_command",
        AsyncMock(
            return_value=AppResponse(
                text="ok", image_url="https://quickchart.io/chart?c=x"
            )
        ),
    ), patch("main.ApiClient"), patch("main.MessagingApi") as mock_messaging_cls:
        mock_api = mock_messaging_cls.return_value
        resp = client.post(
            "/callback",
            content=body,
            headers={"X-Line-Signature": _sign(body)},
        )

    assert resp.status_code == 200
    request = mock_api.reply_message.call_args.args[0]
    messages = request.messages
    assert len(messages) == 2
    assert isinstance(messages[1], ImageMessage)
    assert messages[1].original_content_url == "https://quickchart.io/chart?c=x"
    assert messages[1].preview_image_url == "https://quickchart.io/chart?c=x"


def test_callback_reply_message_failure_returns_200(client, caplog):
    body = _message_body()
    with patch.object(
        main.router, "route_command", AsyncMock(return_value=AppResponse(text="ok"))
    ), patch("main.ApiClient"), patch("main.MessagingApi") as mock_messaging_cls:
        mock_api = mock_messaging_cls.return_value
        mock_api.reply_message.side_effect = Exception("boom")
        with caplog.at_level(logging.ERROR):
            resp = client.post(
                "/callback",
                content=body,
                headers={"X-Line-Signature": _sign(body)},
            )

    assert resp.status_code == 200
    mock_api.reply_message.assert_called_once()
    assert "Failed to send LINE reply" in caplog.text


def test_callback_quick_reply_on_last_message_without_image(client):
    """Quick replies attach to the primary text message when no image follows."""
    from linebot.v3.messaging import TextMessage, QuickReply
    from models.response import QuickReplyAction

    body = _message_body()
    response = AppResponse(
        text="ok",
        quick_replies=[QuickReplyAction(label="🔍 X", text="เจาะดู X")],
    )
    with patch.object(main.router, "route_command", AsyncMock(return_value=response)), \
         patch("main.ApiClient"), patch("main.MessagingApi") as mock_messaging_cls:
        mock_api = mock_messaging_cls.return_value
        resp = client.post(
            "/callback",
            content=body,
            headers={"X-Line-Signature": _sign(body)},
        )

    assert resp.status_code == 200
    messages = mock_api.reply_message.call_args.args[0].messages
    assert len(messages) == 1
    assert isinstance(messages[0], TextMessage)
    assert isinstance(messages[0].quick_reply, QuickReply)
    assert messages[0].quick_reply.items[0].action.label == "🔍 X"
    assert messages[0].quick_reply.items[0].action.text == "เจาะดู X"


def test_callback_quick_reply_on_image_when_image_present(client):
    """Quick replies must be on the LAST message (the image), not the text."""
    from linebot.v3.messaging import TextMessage, ImageMessage, QuickReply
    from models.response import QuickReplyAction

    body = _message_body()
    response = AppResponse(
        text="ok",
        image_url="https://quickchart.io/chart?c=x",
        quick_replies=[QuickReplyAction(label="🔍 X", text="เจาะดู X")],
    )
    with patch.object(main.router, "route_command", AsyncMock(return_value=response)), \
         patch("main.ApiClient"), patch("main.MessagingApi") as mock_messaging_cls:
        mock_api = mock_messaging_cls.return_value
        resp = client.post(
            "/callback",
            content=body,
            headers={"X-Line-Signature": _sign(body)},
        )

    assert resp.status_code == 200
    messages = mock_api.reply_message.call_args.args[0].messages
    assert len(messages) == 2
    assert isinstance(messages[0], TextMessage)
    assert messages[0].quick_reply is None
    assert isinstance(messages[1], ImageMessage)
    assert isinstance(messages[1].quick_reply, QuickReply)
    assert messages[1].quick_reply.items[0].action.label == "🔍 X"
