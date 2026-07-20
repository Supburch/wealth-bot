import logging
from typing import Dict
from models.user import UserInfo
from services.sheets_service import get_master_sheet_records
from services.cache import cached

logger = logging.getLogger(__name__)


@cached("user_mappings")
async def _fetch_all_users() -> Dict[str, UserInfo]:
    """Fetch user mapping from Master Spreadsheet and return dict keyed by LINE_USER_ID"""
    try:
        records = get_master_sheet_records("Users")
        users = {}
        for row in records:
            user_id = str(row.get("LINE_USER_ID", "")).strip()
            if not user_id:
                continue
            users[user_id] = UserInfo(
                user_id=user_id,
                spreadsheet_id=str(row.get("SPREADSHEET_ID", "")).strip(),
                role=str(row.get("ROLE", "user")).strip().lower(),
                enabled=bool(str(row.get("ENABLED", "")).strip().lower() in ["true", "1", "yes", "y"])
            )
        return users
    except Exception as e:
        logger.error(f"Failed to fetch users from Master Sheet: {e}")
        return {}


async def get_user(user_id: str) -> UserInfo | None:
    """Retrieve UserInfo by LINE_USER_ID. Uses cache internally."""
    users = await _fetch_all_users()
    return users.get(user_id)
