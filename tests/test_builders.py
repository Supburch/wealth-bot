"""Smoke tests for builders/*: each builder runs and returns a non-empty structure."""

from decimal import Decimal

from builders.help_text_builder import build_help_text
from builders.holdings_flex_builder import build_holdings_flex
from builders.portfolio_flex_builder import build_portfolio_flex
from builders.today_flex_builder import build_today_flex
from builders.validation_flex_builder import build_validation_flex
from models.portfolio import (
    HoldingBreakdown,
    PortfolioHoldings,
    PortfolioItem,
    PortfolioResult,
    TodaySummary,
)
from models.validation import ValidationIssue, ValidationSummary


def test_build_help_text():
    text = build_help_text()
    assert isinstance(text, str)
    assert text.strip()


def test_build_holdings_flex():
    holding = HoldingBreakdown(
        symbol="AAPL", market_value=1000.0, weight=50.0, cost=800.0, profit_pct=25.0
    )
    flex = build_holdings_flex([holding])
    assert flex["type"] == "bubble"
    assert flex["body"]["contents"]


def test_build_portfolio_flex():
    item = PortfolioItem(
        symbol="AAPL",
        avg_cost=Decimal("100"),
        shares=Decimal("10"),
        current_price=Decimal("150"),
    )
    result = PortfolioResult(
        us_holdings=PortfolioHoldings(items=[item]),
        dr_value=Decimal("500"),
        dr_positions=1,
        dr_skipped=0,
    )
    flex = build_portfolio_flex(result)
    assert flex["type"] == "bubble"
    assert flex["body"]["contents"]

    texts = [
        c["text"]
        for c in flex["body"]["contents"]
        if isinstance(c, dict) and c.get("type") == "text"
    ]
    assert not any("รอตรวจสอบ" in t for t in texts)


def test_build_portfolio_flex_shows_dr_warning():
    item = PortfolioItem(
        symbol="AAPL",
        avg_cost=Decimal("100"),
        shares=Decimal("10"),
        current_price=Decimal("150"),
    )
    result = PortfolioResult(
        us_holdings=PortfolioHoldings(items=[item]),
        dr_value=Decimal("500"),
        dr_positions=1,
        dr_skipped=2,
    )
    flex = build_portfolio_flex(result)

    texts = [
        c["text"]
        for c in flex["body"]["contents"]
        if isinstance(c, dict) and c.get("type") == "text"
    ]
    assert any("รอตรวจสอบ" in t for t in texts)


def test_build_portfolio_flex_shows_us_profit_row():
    item = PortfolioItem(
        symbol="AAPL",
        avg_cost=Decimal("100"),
        shares=Decimal("10"),
        current_price=Decimal("150"),
    )
    result = PortfolioResult(
        us_holdings=PortfolioHoldings(items=[item]),
        dr_value=Decimal("500"),
        dr_positions=1,
        dr_skipped=0,
    )
    flex = build_portfolio_flex(result)

    profit_value = None
    for c in flex["body"]["contents"]:
        if not (isinstance(c, dict) and c.get("type") == "box"):
            continue
        texts = [
            t.get("text")
            for t in c.get("contents", [])
            if isinstance(t, dict) and t.get("type") == "text"
        ]
        if texts and texts[0] == "กำไร/ขาดทุน":
            profit_value = texts[1]
            break

    assert profit_value is not None
    assert "+฿500" in profit_value
    assert "+50.00%" in profit_value


def test_build_portfolio_flex_shows_dr_profit_row():
    item = PortfolioItem(
        symbol="AAPL",
        avg_cost=Decimal("100"),
        shares=Decimal("10"),
        current_price=Decimal("150"),
    )
    result = PortfolioResult(
        us_holdings=PortfolioHoldings(items=[item]),
        dr_value=Decimal("500"),
        dr_cost=Decimal("400"),
        dr_positions=1,
        dr_skipped=0,
    )
    flex = build_portfolio_flex(result)

    dr_label = None
    dr_value_text = None
    dr_color = None
    for c in flex["body"]["contents"]:
        if not (isinstance(c, dict) and c.get("type") == "box"):
            continue
        texts = [
            t
            for t in c.get("contents", [])
            if isinstance(t, dict) and t.get("type") == "text"
        ]
        if texts and texts[0].get("text") == "กำไร/ขาดทุน (DR)":
            dr_label = texts[0].get("text")
            dr_value_text = texts[1].get("text")
            dr_color = texts[1].get("color")
            break

    assert dr_label == "กำไร/ขาดทุน (DR)"
    assert "+฿100" in dr_value_text
    assert "+25.00%" in dr_value_text
    assert dr_color == "#2ecc71"


def test_build_today_flex():
    today = TodaySummary(portfolio_value=1000.0, today_profit=50.0, today_profit_pct=5.0)
    flex = build_today_flex(today)
    assert flex["type"] == "bubble"
    assert flex["body"]["contents"]


def test_build_validation_flex():
    summary = ValidationSummary(
        total_rows=1,
        valid_rows=0,
        invalid_rows=1,
        issues=[ValidationIssue(row_index=2, symbol="AAPL", error_message="bad price")],
    )
    flex = build_validation_flex(summary)
    assert flex["type"] == "bubble"
    assert flex["body"]["contents"]
