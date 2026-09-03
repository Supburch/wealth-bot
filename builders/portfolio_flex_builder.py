from decimal import Decimal
from models.portfolio import PortfolioHoldings


def build_portfolio_flex(
    portfolio: PortfolioHoldings,
    fx_rate: Decimal | None = None,
) -> dict:
    """Return raw Flex Message contents dict. Does not wrap AppResponse."""
    sign = "+" if portfolio.total_profit >= 0 else ""
    profit_color = "#2ecc71" if portfolio.total_profit >= 0 else "#e74c3c"

    def row(label: str, value: str, color: str = "#555555") -> dict:
        return {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "text", "text": label, "color": "#aaaaaa", "size": "sm", "flex": 5},
                {"type": "text", "text": value, "color": color, "size": "sm", "flex": 5, "align": "end"}
            ]
        }

    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": "💰 พอร์ต",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#1a1a2e"
                },
                {"type": "separator"},
                row("มูลค่าพอร์ต", f"฿{portfolio.total_market_value:,.0f}"),
                row("ต้นทุน",      f"฿{portfolio.total_cost:,.0f}"),
                row("กำไร",       f"{sign}฿{portfolio.total_profit:,.0f}", profit_color),
                row("ผลตอบแทน",  f"{sign}{portfolio.roi_percent}%", profit_color),
                row("จำนวน",     f"{portfolio.total_positions} หลักทรัพย์"),
                *([row("เรท", f"฿{fx_rate:.2f}/USD", "#888888")] if fx_rate is not None else []),
            ]
        }
    }
