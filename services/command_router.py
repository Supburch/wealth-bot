from typing import Dict
from handlers.base import CommandHandler
from models.response import AppResponse
from core.messages import UNKNOWN_COMMAND

class CommandRouter:
    def __init__(self, routes: Dict[str, CommandHandler]):
        self.routes = routes

    def normalize_command(self, raw_command: str) -> str:
        command = raw_command.strip().lower()
        if command.startswith("หุ้น "):
            command = command.replace("หุ้น ", "", 1).strip()
        return command

    async def route_command(self, user_id: str, raw_command: str) -> AppResponse:
        command = self.normalize_command(raw_command)
        handler = self.routes.get(command)
        
        if handler:
            return await handler.handle(user_id)
            
        return AppResponse(text=UNKNOWN_COMMAND)
