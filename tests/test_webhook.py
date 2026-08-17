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
