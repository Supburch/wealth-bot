"""
test_command_router.py — Unit tests for CommandRouter (P2.4c).

Covers the centralized catch-all: unexpected exceptions from a handler or the
symbol fallback are converted to a friendly UNEXPECTED_ERROR instead of crashing.
"""
from models.response import AppResponse
from core.messages import UNEXPECTED_ERROR, UNKNOWN_COMMAND


class _BoomHandler:
    async def handle(self, user_id: str) -> AppResponse:
        raise RuntimeError("boom")


class _OkHandler:
    async def handle(self, user_id: str) -> AppResponse:
        return AppResponse(text="ok")


async def _boom_symbol(user_id: str, command: str) -> AppResponse:
    raise ValueError("symbol boom")


async def test_route_command_normal_path():
    from services.command_router import CommandRouter
    router = CommandRouter(routes={"ping": _OkHandler()})
    result = await router.route_command("U1", "ping")
    assert result.text == "ok"


async def test_route_command_unknown_command():
    from services.command_router import CommandRouter
    router = CommandRouter(routes={})
    result = await router.route_command("U1", "zzz")
    assert result.text == UNKNOWN_COMMAND


async def test_route_command_handler_exception_returns_unexpected_error():
    from services.command_router import CommandRouter
    router = CommandRouter(routes={"พอร์ต": _BoomHandler()})
    result = await router.route_command("U1", "พอร์ต")
    assert result.text == UNEXPECTED_ERROR


async def test_route_command_symbol_exception_returns_unexpected_error():
    from services.command_router import CommandRouter
    router = CommandRouter(routes={}, symbol_handler=_boom_symbol)
    result = await router.route_command("U1", "AAPL")
    assert result.text == UNEXPECTED_ERROR
