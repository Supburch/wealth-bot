import logging
from models.response import AppResponse
from core.enums import ResponseType
from core.messages import UNEXPECTED_ERROR
from builders.help_text_builder import build_help_text

logger = logging.getLogger(__name__)

class HelpHandler:
    async def handle(self, user_id: str) -> AppResponse:
        try:
            text = build_help_text()
            return AppResponse(type=ResponseType.TEXT, text=text)
        except Exception:
            logger.exception("Unexpected error in HelpHandler")
            return AppResponse(type=ResponseType.TEXT, text=UNEXPECTED_ERROR)
