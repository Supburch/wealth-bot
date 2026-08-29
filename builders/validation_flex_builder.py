from models.validation import ValidationSummary, ValidationIssue

def build_validation_flex(summary: ValidationSummary) -> dict:
    """Build Flex Message bubble for the validation report."""
    
    # Header color: Green if valid, Red if invalid
    header_color = "#2ecc71" if summary.is_valid else "#e74c3c"
    title = "✅ ข้อมูลถูกต้อง" if summary.is_valid else "⚠️ พบข้อผิดพลาด"

    def issue_row(issue: ValidationIssue) -> dict:
        return {
            "type": "box",
            "layout": "vertical",
            "spacing": "xs",
            "margin": "md",
            "contents": [
                {
                    "type": "text",
                    "text": f"แถว {issue.row_index}: {issue.symbol}",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#333333"
                },
                {
                    "type": "text",
                    "text": issue.error_message,
                    "size": "xs",
                    "color": "#e74c3c",
                    "wrap": True
                }
            ]
        }

    # Summary box
    summary_box = {
        "type": "box",
        "layout": "horizontal",
        "margin": "md",
        "contents": [
            {
                "type": "box",
                "layout": "vertical",
                "flex": 1,
                "contents": [
                    {"type": "text", "text": "ทั้งหมด", "size": "xs", "color": "#aaaaaa", "align": "center"},
                    {"type": "text", "text": str(summary.total_rows), "weight": "bold", "size": "md", "color": "#333333", "align": "center"}
                ]
            },
            {
                "type": "box",
                "layout": "vertical",
                "flex": 1,
                "contents": [
                    {"type": "text", "text": "ถูกต้อง", "size": "xs", "color": "#aaaaaa", "align": "center"},
                    {"type": "text", "text": str(summary.valid_rows), "weight": "bold", "size": "md", "color": "#2ecc71", "align": "center"}
                ]
            },
            {
                "type": "box",
                "layout": "vertical",
                "flex": 1,
                "contents": [
                    {"type": "text", "text": "ข้อผิดพลาด", "size": "xs", "color": "#aaaaaa", "align": "center"},
                    {"type": "text", "text": str(summary.invalid_rows), "weight": "bold", "size": "md", "color": "#e74c3c", "align": "center"}
                ]
            }
        ]
    }

    contents = [
        {"type": "text", "text": title, "weight": "bold", "size": "xl", "color": header_color},
        {"type": "separator", "margin": "md"},
        summary_box
    ]

    # Add issues if there are any (limit to top 10 to avoid flex message size limit)
    if not summary.is_valid:
        contents.append({"type": "separator", "margin": "md"})
        contents.append({
            "type": "text", 
            "text": "รายละเอียดข้อผิดพลาด (สูงสุด 10 รายการ):", 
            "size": "xs", 
            "color": "#aaaaaa", 
            "margin": "md"
        })
        
        for issue in summary.issues[:10]:
            contents.append(issue_row(issue))
            
        if len(summary.issues) > 10:
            contents.append({
                "type": "text",
                "text": f"...และอีก {len(summary.issues) - 10} รายการ",
                "size": "xs",
                "color": "#aaaaaa",
                "margin": "md",
                "align": "center"
            })

    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": contents
        }
    }
