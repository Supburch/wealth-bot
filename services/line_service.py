import logging
from config import settings
from services.portfolio_service import (
    get_portfolio_summary, get_top_holdings,
    get_wealth_summary, get_today_summary, get_holding_breakdown,
)
from services.sheets_service import check_sheets_health, invalidate_client
from services.cache import clear_cache, get_last_refresh_time, get_cache_entries_count, CACHE_TTL

logger = logging.getLogger(__name__)

def format_number(num: float, is_currency=False) -> str:
    if num >= 1_000_000 and is_currency:
        return f"{num/1_000_000:.2f}M"
    elif num >= 1_000 and is_currency:
        return f"{num/1_000:.0f}K"
    return f"{num:,.0f}"

async def handle_user_command(user_id: str, raw_command: str) -> str:
    if user_id not in settings.allowed_users_set:
        return "Unauthorized"

    command = raw_command.strip().lower()
    if command.startswith("หุ้น "):
        command = command.replace("หุ้น ", "").strip()

    # ---- ADMIN COMMANDS ----
    if command in ["refresh", "reload"]:
        if user_id not in settings.admin_users_set:
            return "⛔ Unauthorized: สำหรับ Admin เท่านั้น"
            
        if command == "refresh":
            await clear_cache()
            return "✅ Refresh: ล้าง Cache ข้อมูลเรียบร้อยแล้ว"
        else:
            await clear_cache()
            invalidate_client()
            return "🔄 Reload: ล้าง Cache และเชื่อมต่อ Google Sheets ใหม่แล้ว"

    # ---- UTILITY COMMANDS ----
    if command == "ping":
        return "pong"
        
    elif command == "version":
        return f"Wealth Bot\nv{settings.APP_VERSION}"

    # ---- USER COMMANDS ----
    try:
        if command == "พอร์ต":
            data = await get_portfolio_summary()
            sign_profit = "+" if data.profit >= 0 else ""
            return (
                f"💰 Portfolio\n"
                f"มูลค่าพอร์ต:\n฿{data.portfolio_value:,.0f}\n"
                f"ต้นทุน:\n฿{data.cost_basis:,.0f}\n"
                f"กำไร:\n{sign_profit}฿{data.profit:,.0f}\n"
                f"ผลตอบแทน:\n{sign_profit}{data.profit_pct}%"
            )
            
        elif command == "สรุป":
            data = await get_wealth_summary()
            sign_profit = "+" if data.summary.profit >= 0 else ""
            top_holdings_str = "\n".join([h.symbol for h in data.top_holdings[:3]])
            return (
                f"💰 Wealth Summary\n"
                f"Portfolio Value:\n฿{format_number(data.summary.portfolio_value, True)}\n"
                f"Profit:\n{sign_profit}{data.summary.profit_pct}%\n"
                f"Cash:\n฿{format_number(data.summary.cash, True)}\n"
                f"Top Holdings:\n{top_holdings_str}"
            )

        elif command == "วันนี้":
            data = await get_today_summary()
            sign_today = "+" if data.today_profit >= 0 else ""
            return (
                f"Portfolio\n฿{format_number(data.portfolio_value, True)}\n\n"
                f"Today:\n{sign_today}{data.today_profit:,.0f}\n\n"
                f"{sign_today}{data.today_profit_pct}%"
            )

        elif command == "ถืออะไร":
            data = await get_top_holdings()
            holdings_str = "\n".join([f"{h.symbol} {h.weight:g}%" for h in data])
            return f"Top Holdings\n\n{holdings_str}"

        elif command == "status":
            sheets_ok = await check_sheets_health()
            return (
                f"📊 System Status\n\n"
                f"Sheets: {'OK' if sheets_ok else 'ERROR'}\n"
                f"Cache: OK\n"
                f"Entries: {get_cache_entries_count()}\n"
                f"Last Refresh: {get_last_refresh_time()}\n"
                f"Cache TTL: {CACHE_TTL}s"
            )

        elif command in ["ช่วยเหลือ", "help"]:
            return (
                "คำสั่งทั้งหมด\n\n"
                "พอร์ต\nสรุป\nวันนี้\nถืออะไร\n\n"
                "[Symbol] เพื่อดูข้อมูลรายตัว\nเช่น AAPL, NVDA, BTC\n\n"
                "-- Utility --\n"
                "ping, version\n\n"
                "-- Admin --\n"
                "refresh, reload, status"
            )

        else:
            breakdown = await get_holding_breakdown(command)
            if breakdown:
                sign_profit = "+" if breakdown.profit_pct >= 0 else ""
                return (
                    f"{breakdown.symbol}\n\n"
                    f"Market Value:\n฿{breakdown.market_value:,.0f}\n\n"
                    f"Weight:\n{breakdown.weight:g}%\n\n"
                    f"Cost:\n฿{breakdown.cost:,.0f}\n\n"
                    f"Profit:\n{sign_profit}{breakdown.profit_pct}%"
                )
            
            return "คำสั่งไม่ถูกต้อง พิมพ์ 'help' เพื่อดูคำสั่งทั้งหมด"

    except Exception as e:
        logger.exception("Error handling user command")
        return "⚠️ ไม่สามารถดึงข้อมูลได้ชั่วคราว\nกรุณาลองใหม่อีกครั้ง"
