from decimal import Decimal
from models.portfolio import PortfolioResult


def build_portfolio_flex(
    portfolio: PortfolioResult,
    fx_rate: Decimal | None = None,
) -> dict:
    """Return raw Flex Message contents for the 'พอร์ต' command.

    Shows Stock USA (with its profit/loss) and Stock DR as separate blocks plus
    a combined total, and appends a warning when some DR rows are pending review
    (skipped). The profit/loss line applies to the Stock USA block only — DR
    positions carry no cost basis, so no combined profit is computed.
    """

    def row(label: str, value: str, color: str = "#555555", weight: str | None = None) -> dict:
        value_text: dict = {
            "type": "text",
            "text": value,
            "color": color,
            "size": "sm",
            "flex": 5,
            "align": "end",
        }
        if weight is not None:
            value_text["weight"] = weight
        return {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "text", "text": label, "color": "#aaaaaa", "size": "sm", "flex": 5},
                value_text,
            ],
        }

    us_profit = portfolio.us_holdings.total_profit
    roi = portfolio.us_holdings.roi_percent
    sign = "+" if us_profit >= 0 else ""
    profit_color = "#2ecc71" if us_profit >= 0 else "#e74c3c"

    contents: list[dict] = [
        {
            "type": "text",
            "text": "💰 พอร์ต",
            "weight": "bold",
            "size": "xl",
            "color": "#1a1a2e",
        },
        {"type": "separator"},
        row("🇺🇸 Stock USA", f"฿{portfolio.us_value:,.0f}"),
        row("กำไร/ขาดทุน", f"{sign}฿{us_profit:,.0f} ({sign}{roi}%)", profit_color),
        row("🌏 Stock DR", f"฿{portfolio.dr_value:,.0f}"),
        {"type": "separator"},
        row("💰 รวมทั้งหมด", f"฿{portfolio.total_value:,.0f}", color="#1a1a2e", weight="bold"),
        row("จำนวน", f"{portfolio.total_positions} หลักทรัพย์"),
    ]
    if fx_rate is not None:
        contents.append(row("เรท", f"฿{fx_rate:.2f}/USD", "#888888"))

    if portfolio.dr_skipped > 0:
        contents.append(
            {
                "type": "text",
                "text": f"⚠️ มี {portfolio.dr_skipped} รายการ DR รอตรวจสอบ (ไม่รวมในยอด)",
                "color": "#e67e22",
                "size": "sm",
                "wrap": True,
            }
        )

    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": contents,
        },
    }

