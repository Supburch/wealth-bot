"""chart_service.py — QuickChart.io chart-URL builders for LINE image messages.

The two public builders are pure functions: they take already-computed
labels/values and return a QuickChart GET URL string. No portfolio math lives
here — handlers pass in the labels/values they already derived from the
portfolio/allocation services.

Chart styling uses QuickChart's defaults (no custom colors), per the product
decision to keep charts simple and dependency-free (free hosted endpoint, no
self-hosting required).
"""

import json
import logging
from urllib.parse import quote

from services.cache import cached

logger = logging.getLogger(__name__)

QUICKCHART_ENDPOINT = "https://quickchart.io/chart"


def _build_chart_url(chart_config: dict) -> str:
    """Serialize a Chart.js config into a QuickChart GET URL."""
    encoded = quote(json.dumps(chart_config, separators=(",", ":")), safe="")
    return f"{QUICKCHART_ENDPOINT}?c={encoded}"


def build_pie_chart_url(labels: list[str], values: list[float]) -> str:
    """Build a pie-chart URL for the 'สัดส่วน' command (asset-class mix).

    Percentages are computed here in Python (no JS ``formatter`` is embedded in
    the URL) and appended to the legend labels, e.g. ``"Cash (25.0%)"``. Slice
    data labels are disabled so raw THB values don't render on the chart.
    """
    total = sum(values)
    labeled = (
        [f"{label} ({value / total * 100:.1f}%)" for label, value in zip(labels, values)]
        if total
        else list(labels)
    )

    config = {
        "type": "pie",
        "data": {
            "labels": labeled,
            "datasets": [{"data": values}],
        },
        "options": {
            "plugins": {
                "legend": {"display": True},
                "datalabels": {"display": False},
            }
        },
    }
    return _build_chart_url(config)


def build_bar_chart_url(labels: list[str], values: list[float]) -> str:
    """Build a bar-chart URL for the 'พอร์ต' command (Stock USA vs Stock DR).

    Values are THB-denominated. The single dataset carries an explicit label and
    the legend is disabled, so QuickChart no longer renders an "undefined"
    legend entry.
    """
    config = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{"label": "มูลค่า (บาท)", "data": values}],
        },
        "options": {
            "plugins": {
                "legend": {"display": False},
            }
        },
    }
    return _build_chart_url(config)


@cached("chart_url")
async def get_cached_chart_url(
    chart_type: str, labels: list[str], values: list[float]
) -> str:
    """Build and cache a chart URL keyed by (type, labels, values).

    Uses the same TTL as the source data (the default ``CACHE_TTL``) so the URL
    isn't rebuilt on every request within the TTL window.
    """
    if chart_type == "pie":
        return build_pie_chart_url(labels, values)
    if chart_type == "bar":
        return build_bar_chart_url(labels, values)
    raise ValueError(f"Unknown chart type: {chart_type!r}")
