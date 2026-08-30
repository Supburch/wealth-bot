"""Tests for the `/health` endpoint (HEAD + GET)."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import main


def test_health_head_returns_200():
    with patch("main.check_sheets_health", AsyncMock(return_value=True)):
        with TestClient(main.app) as client:
            resp = client.head("/health")

    assert resp.status_code == 200


def test_health_get_returns_200():
    with patch("main.check_sheets_health", AsyncMock(return_value=True)):
        with TestClient(main.app) as client:
            resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
