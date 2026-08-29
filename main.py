import time
import logging
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, Request, Header, HTTPException
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage, FlexMessage, FlexContainer,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from config import settings
from core.enums import ResponseType
from core.correlation import RequestIdFilter, request_id_var
from core.redaction import mask_id, redact_text
from models.health import HealthDto
from models.response import AppResponse
from services.command_router import build_router
from services.sheets_service import check_sheets_health
from services.cache import get_cache_entries_count

class ExtraFieldFormatter(logging.Formatter):
    """Render ``extra={...}`` keys as key=value pairs on the log line.

    Standard :class:`logging.LogRecord` attributes are excluded so only the
    caller-supplied ``extra`` fields (e.g. ``spreadsheet_id``, ``error_type``)
    are surfaced in the output.
    """

    _STANDARD_ATTRS = frozenset({
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "msg", "name", "pathname", "process", "processName", "relativeCreated",
        "request_id", "stack_info", "taskName", "thread", "threadName", "message",
    })

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            key: value
            for key, value in vars(record).items()
            if key not in self._STANDARD_ATTRS
        }
        if extras:
            rendered = " ".join(
                f"{key}={value}" for key, value in sorted(extras.items())
            )
            return f"{base} [{rendered}]"
        return base


handler = logging.StreamHandler()
handler.setFormatter(
    ExtraFieldFormatter(fmt="%(levelname)s:%(name)s:%(request_id)s:%(message)s")
)
handler.addFilter(RequestIdFilter())
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    handlers=[handler],
    force=True,
)
logger = logging.getLogger(__name__)

START_TIME = time.time()

# ── Router (initialized at startup) ───────────────────────────────────────────
router = build_router(settings.APP_VERSION)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Wealth Bot v%s...", settings.APP_VERSION)
    yield
    logger.info("Shutting down Wealth Bot...")


app = FastAPI(title="Wealth Bot", lifespan=lifespan)
line_config = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(settings.LINE_CHANNEL_SECRET)


def _build_line_message(response: AppResponse):
    """Convert AppResponse to the appropriate LINE SDK message object."""
    if response.type == ResponseType.RICH and response.contents:
        return FlexMessage(
            alt_text=response.alt_text or "Portfolio",
            contents=FlexContainer.from_dict(response.contents),
        )
    return TextMessage(text=response.text or "")


@app.get("/health", response_model=HealthDto)
async def health_check():
    sheets_ok = await check_sheets_health()
    uptime = int(time.time() - START_TIME)
    return HealthDto(
        status="ok" if sheets_ok else "degraded",
        google_sheets="ok" if sheets_ok else "error",
        cache_entries=get_cache_entries_count(),
        uptime_seconds=uptime,
        version=settings.APP_VERSION,
    )


@app.post("/callback")
async def line_webhook(request: Request, x_line_signature: str = Header(None)):
    token = request_id_var.set(uuid4().hex[:8])
    try:
        # LINE always sends this header. When it is missing, the request did not
        # come from LINE, so fail closed with 401. Guarding here also avoids a 500:
        # the SDK raises AttributeError (not InvalidSignatureError) when signature
        # is None.
        if not x_line_signature:
            raise HTTPException(status_code=401, detail="Missing signature")

        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="Empty body")

        try:
            events = parser.parse(body.decode("utf-8"), x_line_signature)
        except InvalidSignatureError:
            raise HTTPException(status_code=401, detail="Invalid signature")

        with ApiClient(line_config) as api_client:
            line_bot_api = MessagingApi(api_client)
            for event in events:
                if not isinstance(event, MessageEvent):
                    continue
                if not isinstance(event.message, TextMessageContent):
                    continue

                user_id = event.source.user_id
                text = event.message.text
                logger.info("Received message from %s", mask_id(user_id))
                logger.debug("Message text: %s", redact_text(text))

                response = await router.route_command(user_id, text)
                try:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[_build_line_message(response)],
                        )
                    )
                except Exception:
                    logger.exception("Failed to send LINE reply for user %s", mask_id(user_id))
    finally:
        request_id_var.reset(token)

