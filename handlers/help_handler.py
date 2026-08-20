from models.response import AppResponse
from core.enums import ResponseType
from builders.help_text_builder import build_help_text


class HelpHandler:
    async def handle(self, user_id: str) -> AppResponse:
        output = build_help_text()
        return AppResponse(type=ResponseType.TEXT, text=output)
