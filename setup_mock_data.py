import json
import gspread
from google.oauth2.service_account import Credentials
from config import settings

def setup_mock_data():
    print("🔄 กำลังเชื่อมต่อ Google Sheets...")
    
    # 1. Auth ด้วย Credentials เดิมที่ตั้งค่าไว้
    creds_dict = json.loads(settings.GOOGLE_CREDENTIALS_JSON)
    # เพิ่ม Scope ให้สามารถเขียนข้อมูลได้สำหรับการ Setup
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # 2. เปิด Spreadsheet ตาม ID ใน .env
    sh = client.open_by_key(settings.SPREADSHEET_ID)
    
    # 3. ข้อมูล Mock Data
    sheets_data = {
        "PortfolioSummary": [
            ["Metric", "Value"],
            ["PortfolioValue", 7450000],
            ["CostBasis", 6200000],
            ["Profit", 1250000],
            ["ProfitPct", 20.16],
            ["Cash", 450000]
        ],
        "TodaySummary": [
            ["Metric", "Value"],
            ["PortfolioValue", 7450000],
            ["TodayProfit", 35000],
            ["TodayProfitPct", 0.47]
        ],
        "AssetAllocation": [
            ["AssetClass", "Percent"],
            ["US Stocks", 55],
            ["Crypto", 20],
            ["ETF", 15],
            ["Cash", 10]
        ],
        "HoldingsBreakdown": [
            ["Symbol", "MarketValue", "Weight", "Cost", "ProfitPct"],
            ["NVDA", 1350000, 18.1, 720000, 87.5],
            ["BTC", 1100000, 14.8, 850000, 29.4],
            ["AAPL", 950000, 12.7, 720000, 31.9],
            ["MSTR", 800000, 10.7, 500000, 60.0],
            ["VOO", 1125000, 15.1, 1000000, 12.5],
            ["NEM", 600000, 8.0, 550000, 9.1],
            ["XAU", 500000, 6.7, 450000, 11.1]
        ]
    }
    
    # 4. วนลูปสร้าง Sheet และใส่ข้อมูล
    for sheet_title, data in sheets_data.items():
        try:
            worksheet = sh.worksheet(sheet_title)
            print(f"📝 พบ Sheet '{sheet_title}' แล้ว กำลังล้างข้อมูลเก่าและอัปเดตใหม่...")
        except gspread.exceptions.WorksheetNotFound:
            print(f"✨ สร้าง Sheet ใหม่: '{sheet_title}'...")
            worksheet = sh.add_worksheet(title=sheet_title, rows=100, cols=20)
        
        worksheet.clear()
        worksheet.update(values=data, range_name="A1")
        print(f"✅ ใส่ข้อมูลใน '{sheet_title}' สำเร็จ")
        
    print("\n🎉 สร้างข้อมูล Mock ทั้ง 4 Sheet เสร็จสมบูรณ์แล้วค่ะ!")

if __name__ == "__main__":
    setup_mock_data()
