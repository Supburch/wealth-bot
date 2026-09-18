from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from core.enums import ResponseType


class QuickReplyAction(BaseModel):
    """A LINE quick-reply button: label shown + text sent when tapped."""

    label: str
    text: str


class AppResponse(BaseModel):
    type: ResponseType = ResponseType.TEXT
    text: Optional[str] = None
    alt_text: Optional[str] = None
    contents: Optional[Dict[str, Any]] = None
    image_url: Optional[str] = None
    quick_replies: Optional[List[QuickReplyAction]] = None
