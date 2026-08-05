from models.portfolio import HoldingBreakdown


def build_holdings_flex(
    holdings: list[HoldingBreakdown],
    title: str = "📋 Holdings",
    limit: int = 10,
) -> dict:
    """Build Flex Message bubble listing holdings with symbol, weight, and P/L%."""

    def holding_row(h: HoldingBreakdown) -> dict:
        sign = "+" if h.profit_pct >= 0 else ""
        color = "#2ecc71" if h.profit_pct >= 0 else "#e74c3c"
        return {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "text", "text": h.symbol, "size": "sm", "flex": 4, "color": "#333333"},
                {"type": "text", "text": f"{h.weight:g}%", "size": "sm", "flex": 3, "align": "center", "color": "#555555"},
                {"type": "text", "text": f"{sign}{h.profit_pct:.2f}%", "size": "sm", "flex": 3, "align": "end", "color": color},
            ],
        }

    header_row = {
        "type": "box",
        "layout": "horizontal",
        "contents": [
            {"type": "text", "text": "Symbol", "size": "xs", "color": "#aaaaaa", "flex": 4},
            {"type": "text", "text": "Weight", "size": "xs", "color": "#aaaaaa", "flex": 3, "align": "center"},
            {"type": "text", "text": "P/L%", "size": "xs", "color": "#aaaaaa", "flex": 3, "align": "end"},
        ],
    }

    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {"type": "text", "text": title, "weight": "bold", "size": "xl", "color": "#1a1a2e"},
                {"type": "separator"},
                header_row,
                *[holding_row(h) for h in holdings[:limit]],
            ],
        },
    }
