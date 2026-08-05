from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from core.enums import ResponseType

class AppResponse(BaseModel):
    type: ResponseType = ResponseType.TEXT
    text: Optional[str] = None
    alt_text: Optional[str] = None
    contents: Optional[Dict[str, Any]] = None
