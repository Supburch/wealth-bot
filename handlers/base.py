from typing import Protocol
from models.response import AppResponse

class CommandHandler(Protocol):
    async def handle(self, user_id: str) -> AppResponse:
        ...
