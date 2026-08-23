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
    flex = build_portfolio_flex(PortfolioHoldings(items=[item]))
    assert flex["type"] == "bubble"
    assert flex["body"]["contents"]


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
