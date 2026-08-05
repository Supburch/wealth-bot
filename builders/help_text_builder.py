def build_help_text() -> str:
    """Return the full command list. Does not wrap AppResponse."""
    return (
        "คำสั่งทั้งหมด\n\n"
        "พอร์ต — มูลค่า, ต้นทุน, กำไร\n"
        "สรุป — สรุปพอร์ตและ top holdings\n"
        "วันนี้ — กำไรวันนี้\n"
        "ถืออะไร / top — รายการหุ้นทั้งหมด\n"
        "สัดส่วน — สัดส่วนพอร์ต\n"
        "เงินสด — เงินสดในพอร์ต\n"
        "winners — หุ้นกำไรสูงสุด\n"
        "losers — หุ้นขาดทุนสูงสุด\n\n"
        "[Symbol] เพื่อดูข้อมูลรายตัว\n"
        "เช่น AAPL, NVDA, BTC\n\n"
        "-- Utility --\n"
        "ping, version\n\n"
        "-- Admin --\n"
        "refresh, reload, status\n"
        "validate / ตรวจสอบ — ตรวจสอบข้อมูลพอร์ต"
    )

