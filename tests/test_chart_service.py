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


def test_build_pie_chart_url_shows_percentage_labels():
    labels = ["Cash", "Stock USA", "Stock DR"]
    values = [100.0, 200.0, 50.0]
    url = build_pie_chart_url(labels, values)
    config = _decode_config(url)
    assert config["type"] == "pie"
    assert config["data"]["labels"] == [
        "Cash (28.6%)",
        "Stock USA (57.1%)",
        "Stock DR (14.3%)",
    ]
    assert config["data"]["datasets"] == [{"data": values}]
    # Raw THB values must not be rendered on the slices.
    assert config["options"]["plugins"]["datalabels"]["display"] is False


def test_build_pie_chart_url_zero_total_keeps_plain_labels():
    labels = ["Cash", "Stock USA"]
    values = [0.0, 0.0]
    url = build_pie_chart_url(labels, values)
    config = _decode_config(url)
    assert config["data"]["labels"] == labels


def test_build_bar_chart_url_has_label_and_hides_legend():
    labels = ["Stock USA", "Stock DR"]
    values = [13176.0, 5000.0]
    url = build_bar_chart_url(labels, values)
    config = _decode_config(url)
    assert config["type"] == "bar"
    assert config["data"]["labels"] == labels
    dataset = config["data"]["datasets"][0]
    assert dataset["label"] == "มูลค่า (บาท)"
    assert dataset["data"] == values
    # Legend disabled so no "undefined" entry is rendered.
    assert config["options"]["plugins"]["legend"]["display"] is False


async def test_get_cached_chart_url_returns_url_for_type():
    url = await get_cached_chart_url("pie", ["Cash"], [100.0])
    assert url.startswith("https://quickchart.io/chart?c=")


async def test_get_cached_chart_url_unknown_type_raises():
    with pytest.raises(ValueError):
        await get_cached_chart_url("line", ["a"], [1.0])
