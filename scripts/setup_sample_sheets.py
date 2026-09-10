"""setup_sample_sheets.py — create/update Wealth Bot sample data in Google Sheets.

SAMPLE DATA ONLY. This script never touches production spreadsheets — it
writes exclusively to dedicated TEST spreadsheets that you must provide
explicitly. If a test id is missing (or equals a production id), the script
aborts before doing anything.

Idempotent: clears and rewrites the configured tabs each run.

Prerequisites (in ``.env``):
    GOOGLE_CREDENTIALS_JSON        — service-account key (required by config)
    TEST_MASTER_SPREADSHEET_ID     — dedicated TEST master spreadsheet id (required)
    TEST_SPREADSHEET_ID            — dedicated TEST portfolio spreadsheet id (required)

What it writes:
    TEST Master Spreadsheet    -> ``Users`` tab (sample admin + sample user)
    TEST Portfolio Spreadsheet -> ``Portfolio``, ``PortfolioSummary``,
                                  ``TodaySummary``, ``HoldingsBreakdown``,
                                  ``AssetAllocation``
    (``ValidationResult`` is intentionally NOT created; the ``validate``
     command creates it automatically on first use.)

Run from the repo root:  python scripts/setup_sample_sheets.py
"""

import json
import sys
from pathlib import Path

# Run as `python scripts/setup_sample_sheets.py` from the repo root: make the
# project root importable so `config` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gspread
from google.oauth2.service_account import Credentials

from config import settings

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Sample data (numbers are internally consistent) ────────────────────────────

# Portfolio!A2:D  →  Symbol, AvgCost, Shares, CurrentPrice
PORTFOLIO = [
    ["Symbol", "AvgCost", "Shares", "CurrentPrice"],
    ["NVDA", 425, 2000, 800],
    ["AAPL", 150, 6000, 200],
    ["VOO", 450, 2200, 500],
    ["BTC", 800000, 1, 1000000],
    ["MSTR", 1100, 500, 1800],
    ["NEM", 60, 10000, 65],
    ["XAU", 200, 2500, 220],
]

# PortfolioSummary  →  Metric | Value
PORTFOLIO_SUMMARY = [
    ["Metric", "Value"],
    ["PortfolioValue", 7450000],
    ["CostBasis", 5190000],
    ["Profit", 1810000],
    ["ProfitPct", 34.9],
    ["Cash", 450000],
]

# TodaySummary  →  Metric | Value
TODAY_SUMMARY = [
    ["Metric", "Value"],
    ["PortfolioValue", 7450000],
    ["TodayProfit", 45000],
    ["TodayProfitPct", 0.6],
]

# HoldingsBreakdown  →  header row + one row per holding
HOLDINGS_BREAKDOWN = [
    ["Symbol", "MarketValue", "Weight", "Cost", "ProfitPct"],
    ["NVDA", 1600000, 21.5, 850000, 88.2],
    ["AAPL", 1200000, 16.1, 900000, 33.3],
    ["VOO", 1100000, 14.8, 990000, 11.1],
    ["BTC", 1000000, 13.4, 800000, 25.0],
    ["MSTR", 900000, 12.1, 550000, 63.6],
    ["NEM", 650000, 8.7, 600000, 8.3],
    ["XAU", 550000, 7.4, 500000, 10.0],
]

# AssetAllocation  →  Type | Value (raw value per asset class; the bot
# computes weights/percentages from these values). Add a row to add a type.
ASSET_ALLOCATION = [
    ["Type", "Value"],
    ["Cash", 895541],
    ["Stock USA", 877850],
    ["Stock Worth (DR)", 844900],
    ["Crypto (Holding)", 212113],
    ["FX (OI)", 85578],
]

# Placeholders — replace with real LINE user IDs before using the bot.
PLACEHOLDER_ADMIN = "REPLACE_WITH_LINE_USER_ID_ADMIN"
PLACEHOLDER_USER = "REPLACE_WITH_LINE_USER_ID_USER"


def _authorize() -> tuple[gspread.Client, str]:
    creds_dict = json.loads(settings.GOOGLE_CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds), str(creds_dict.get("client_email", "unknown"))


def _require_test_sheet_id(name: str, value: str, production_value: str) -> str:
    """Return the test sheet id, refusing to run unless it is set and distinct
    from the production id.

    This is the safety net: sample data must never be written to production.
    """
    value = (value or "").strip()
    if not value:
        sys.exit(
            f"\n❌ Refusing to run: {name} is not set.\n"
            "   Set it in .env (or the environment) to a dedicated TEST "
            "spreadsheet id.\n"
            "   This script writes SAMPLE data only and will not touch "
            "production ids.\n"
        )
    if production_value and value == production_value.strip():
        sys.exit(
            f"\n❌ Refusing to run: {name} equals the production spreadsheet id.\n"
            "   Point it at a dedicated TEST spreadsheet instead.\n"
        )
    return value


def _confirm_destination(sh: gspread.Spreadsheet, label: str) -> None:
    """Final human checkpoint: require retyping the destination sheet title
    before overwriting anything, so a wrong-but-real spreadsheet id is caught
    by a person instead of slipping past the id guards.
    """
    title = sh.title
    try:
        answer = input(
            f"\n⚠️  About to overwrite {label} '{title}'\n"
            "   Type the sheet title to confirm: "
        )
    except EOFError:
        sys.exit("\n❌ Cancelled: no interactive input to confirm the sheet title.\n")
    if answer.strip() != title:
        sys.exit("\n❌ Cancelled: sheet title did not match — nothing was written.\n")


def _write_sheet(sh: gspread.Spreadsheet, title: str, rows: list[list]) -> None:
    try:
        ws = sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(
            title=title, rows=max(len(rows), 1), cols=max(len(r) for r in rows)
        )
    ws.clear()
    ws.update(values=rows, range_name="A1")
    print(f"  ✓ {title}: {len(rows) - 1} data row(s)")


def main() -> None:
    client, client_email = _authorize()
    print(f"🔑 Service account email: {client_email}")
    print("   → share the TEST spreadsheets with this email (editor).\n")

    test_portfolio_id = _require_test_sheet_id(
        "TEST_SPREADSHEET_ID",
        settings.TEST_SPREADSHEET_ID,
        settings.SPREADSHEET_ID,
    )
    test_master_id = _require_test_sheet_id(
        "TEST_MASTER_SPREADSHEET_ID",
        settings.TEST_MASTER_SPREADSHEET_ID,
        settings.MASTER_SPREADSHEET_ID,
    )

    # 1. TEST Portfolio spreadsheet (per-user)
    portfolio = client.open_by_key(test_portfolio_id)
    _confirm_destination(portfolio, "TEST Portfolio spreadsheet")
    print(f"📈 TEST Portfolio spreadsheet: {portfolio.id}\n")
    _write_sheet(portfolio, "Portfolio", PORTFOLIO)
    _write_sheet(portfolio, "PortfolioSummary", PORTFOLIO_SUMMARY)
    _write_sheet(portfolio, "TodaySummary", TODAY_SUMMARY)
    _write_sheet(portfolio, "HoldingsBreakdown", HOLDINGS_BREAKDOWN)
    _write_sheet(portfolio, "AssetAllocation", ASSET_ALLOCATION)

    # 2. TEST Master spreadsheet (Users tab)
    master = client.open_by_key(test_master_id)
    _confirm_destination(master, "TEST Master spreadsheet")
    print(f"\n🗂  TEST Master spreadsheet: {master.id}\n")
    users = [
        ["LINE_USER_ID", "SPREADSHEET_ID", "ROLE", "ENABLED"],
        [PLACEHOLDER_ADMIN, portfolio.id, "admin", "TRUE"],
        [PLACEHOLDER_USER, portfolio.id, "user", "TRUE"],
    ]
    _write_sheet(master, "Users", users)

    print("\n🎉 Sample data written to TEST spreadsheets successfully.")
    print("   Next steps:")
    print("   1. Replace the LINE_USER_ID placeholders in the TEST 'Users' tab with")
    print("      real IDs if you want to drive a test bot instance.")
    print("   2. Point a test bot at TEST_MASTER_SPREADSHEET_ID / TEST_SPREADSHEET_ID.")
    print("      Production .env ids were NOT touched.")


if __name__ == "__main__":
    main()

