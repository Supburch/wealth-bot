from models.portfolio import TodaySummary


def build_today_flex(data: TodaySummary) -> dict:
    """Build Flex Message bubble for today's performance."""
    sign = "+" if data.today_profit >= 0 else ""
    profit_color = "#2ecc71" if data.today_profit >= 0 else "#e74c3c"

    def row(label: str, value: str, color: str = "#555555") -> dict:
        return {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "text", "text": label, "color": "#aaaaaa", "size": "sm", "flex": 5},
                {"type": "text", "text": value, "color": color, "size": "sm", "flex": 5, "align": "end"},
            ],
        }

    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {"type": "text", "text": "📅 วันนี้", "weight": "bold", "size": "xl", "color": "#1a1a2e"},
                {"type": "separator"},
                row("มูลค่าพอร์ต", f"฿{data.portfolio_value:,.0f}"),
                row("กำไรวันนี้", f"{sign}฿{data.today_profit:,.0f}", profit_color),
                row("ผลตอบแทน", f"{sign}{data.today_profit_pct}%", profit_color),
            ],
        },
    }
