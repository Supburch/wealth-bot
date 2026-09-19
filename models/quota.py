from pydantic import BaseModel
from typing import Optional


class QuotaStatus(BaseModel):
    """Snapshot of LINE Messaging API message quota for the current month."""

    total_usage: int
    quota_limit: Optional[int] = None      # None when the plan is unlimited
    remaining: Optional[int] = None        # None when unlimited
    usage_percent: Optional[float] = None  # 0–100; None when unlimited
    is_low: bool = False                   # True when remaining has crossed the warning threshold
