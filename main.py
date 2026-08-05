import time
import logging
from contextlib import asynccontextmanager
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
from models.health import HealthDto
from models.response import AppResponse
from services.command_router import build_router
from services.sheets_service import check_sheets_health
from services.cache import get_cache_entries_count

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

START_TIME = time.time()

# ── Router (initialized at startup) ───────────────────────────────────────────
router = build_router(settings.APP_VERSION)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting Wealth Bot v{settings.APP_VERSION}...")
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
    body = await request.body()
    try:
        events = parser.parse(body.decode(), x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    with ApiClient(line_config) as api_client:
        line_bot_api = MessagingApi(api_client)
        for event in events:
            if not isinstance(event, MessageEvent):
                continue
            if not isinstance(event.message, TextMessageContent):
                continue

            user_id = event.source.user_id
            text = event.message.text
            logger.info(f"Received message from {user_id}: {text!r}")

            response = await router.route_command(user_id, text)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[_build_line_message(response)],
                )
            )

