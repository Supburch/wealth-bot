"""Tests for services/chart_service.py — QuickChart URL builders."""

import json
from urllib.parse import parse_qs, urlparse

import pytest

from services import cache as cache_module
from services.chart_service import (
    build_bar_chart_url,
    build_pie_chart_url,
    get_cached_chart_url,
)


@pytest.fixture(autouse=True)
async def _reset_cache():
    await cache_module.clear_cache()
    yield
    await cache_module.clear_cache()


def _decode_config(url: str) -> dict:
    """Extract and JSON-decode the ``c`` query param from a QuickChart URL."""
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "quickchart.io"
    assert parsed.path == "/chart"
    encoded = parse_qs(parsed.query)["c"][0]
    return json.loads(encoded)


def test_build_pie_chart_url_encodes_labels_and_values():
    labels = ["Cash", "Stock USA", "Stock DR"]
    values = [100.0, 200.0, 50.0]
    url = build_pie_chart_url(labels, values)
    config = _decode_config(url)
    assert config["type"] == "pie"
    assert config["data"]["labels"] == labels
    assert config["data"]["datasets"] == [{"data": values}]


def test_build_bar_chart_url_encodes_labels_and_values():
    labels = ["Stock USA", "Stock DR"]
    values = [13176.0, 5000.0]
    url = build_bar_chart_url(labels, values)
    config = _decode_config(url)
    assert config["type"] == "bar"
    assert config["data"]["labels"] == labels
    assert config["data"]["datasets"] == [{"data": values}]


async def test_get_cached_chart_url_returns_url_for_type():
    url = await get_cached_chart_url("pie", ["Cash"], [100.0])
    assert url.startswith("https://quickchart.io/chart?c=")


async def test_get_cached_chart_url_unknown_type_raises():
    with pytest.raises(ValueError):
        await get_cached_chart_url("line", ["a"], [1.0])
