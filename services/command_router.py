"""
command_router.py

CommandRouter — maps normalized commands to CommandHandler instances.
Supports a symbol_handler fallback for unrecognized commands (e.g. "AAPL").

Build the production router with build_router().
"""
from typing import Awaitable, Callable

from handlers.base import CommandHandler
from models.response import AppResponse
from core.messages import UNKNOWN_COMMAND


class CommandRouter:
    def __init__(
        self,
        routes: dict[str, CommandHandler],
        symbol_handler: Callable[[str, str], Awaitable[AppResponse]] | None = None,
    ):
        self.routes = routes
        self.symbol_handler = symbol_handler

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
        if self.symbol_handler:
            return await self.symbol_handler(user_id, command)
        return AppResponse(text=UNKNOWN_COMMAND)


def build_router(app_version: str = "1.0.0") -> "CommandRouter":
    """
    Factory: create a fully wired CommandRouter for production use.
    All handler imports are local to defer module loading until first request.
    """
    from handlers.portfolio_handler import PortfolioHandler
    from handlers.help_handler import HelpHandler
    from handlers.today_handler import TodayHandler
    from handlers.wealth_summary_handler import WealthSummaryHandler
    from handlers.holdings_handler import HoldingsHandler, WinnersHandler, LosersHandler
    from handlers.allocation_handler import AllocationHandler
    from handlers.admin_handler import AdminHandler
    from handlers.utility_handler import PingHandler, VersionHandler, CashHandler
    from handlers.symbol_handler import handle_symbol_lookup
    from handlers.validate_handler import ValidateHandler
    from services.portfolio_service import PortfolioService
    from services.validation_service import ValidationService
    from services.writeback_service import WriteBackService
    from repositories.portfolio_repository import PortfolioRepository
    from repositories.validation_result_repository import GoogleSheetResultRepository
    from services.sheets_service import batch_update_values, get_raw_range
    from core.config import AppConfig

    config = AppConfig()

    class _SheetsAdapter:
        """Adapts sheets_service.get_raw_range to the SheetsGateway protocol."""

        def get_sheet_records(
            self, spreadsheet_id: str, range_name: str
        ) -> list[list[str]]:
            return get_raw_range(spreadsheet_id, range_name)

        def batch_update_values(
            self,
            spreadsheet_id: str,
            sheet_title: str,
            rows: list[list[str | int]],
        ) -> None:
            batch_update_values(spreadsheet_id, sheet_title, rows)

    repo = PortfolioRepository(_SheetsAdapter(), config)
    svc = PortfolioService(repo)
    validation_svc = ValidationService(repo)
    validation_result_repo = GoogleSheetResultRepository(_SheetsAdapter(), config)
    writeback_svc = WriteBackService(validation_result_repo)

    routes: dict[str, CommandHandler] = {
        # ── Portfolio commands ───────────────────────────────────────
        "พอร์ต": PortfolioHandler(svc),
        "สรุป": WealthSummaryHandler(),
        "วันนี้": TodayHandler(),
        "ถืออะไร": HoldingsHandler(),
        "top": HoldingsHandler(),
        "สัดส่วน": AllocationHandler(),
        "เงินสด": CashHandler(),
        "winners": WinnersHandler(),
        "losers": LosersHandler(),
        # ── Help ────────────────────────────────────────────────────
        "help": HelpHandler(),
        "ช่วยเหลือ": HelpHandler(),
        # ── Utility ─────────────────────────────────────────────────
        "ping": PingHandler(),
        "version": VersionHandler(app_version),
        # ── Admin ───────────────────────────────────────────────────
        "refresh": AdminHandler("refresh"),
        "reload": AdminHandler("reload"),
        "status": AdminHandler("status"),
        # ── Validation ──────────────────────────────────────────────
        "validate": ValidateHandler(validation_svc, writeback_svc),
        "ตรวจสอบ": ValidateHandler(validation_svc, writeback_svc),
    }

    return CommandRouter(routes=routes, symbol_handler=handle_symbol_lookup)
