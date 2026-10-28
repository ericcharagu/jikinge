from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from loguru import logger

from config import settings
from services.sender_service import PLATFORM
from services.whatsapp.whatsapp_helper import extract_message_details
from services.whatsapp.whatsapp_schema import MessageRequest
from utils.processor import MessageOrchestrator

router = APIRouter(
    prefix="/webhooks",
    tags=["Webhooks"],
)


@router.get("")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Handles webhook verification for the WhatsApp platform."""
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_WEBHOOK_TOKEN:
        return PlainTextResponse(content=hub_challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("")
async def handle_whatsapp_message(
    request: Request, background_tasks: BackgroundTasks
) -> Any:
    """
    Extract details from Whatsapp payload, process the request and return LLM response.
    """
    whatsapp_message_payload = await request.json()
    # logger.info(f"Whatsapp payload is {whatsapp_message_payload}")

    # Creating the message request object
    if not whatsapp_message_payload.get("entry"):
        raise HTTPException(status_code=400, detail="Invalid payload structure")
    background_task_message: MessageRequest = extract_message_details(
        whatsapp_message=whatsapp_message_payload
    )
    try:
        # 1. Initial Setup & Context Gathering
        cache_client = request.app.state.cache_adapter

        if not (
            background_task_message.user_message
            or background_task_message.media_id
            or background_task_message.address_id
        ):
            logger.info("Webhook received, but no processable text message found.")
            return PlainTextResponse("No text message found", status_code=200)

        # Initiating orchestrator class
        orchestrator: MessageOrchestrator = MessageOrchestrator(
            cache_client=cache_client,
            queue_manager=request.app.state.queue_manager,
            platform=PLATFORM.WHATSAPP,
        )
        # Queue the processing and response to happen in the background
        background_tasks.add_task(
            orchestrator.handle_request, request, background_task_message
        )

        logger.info("Webhook acknowledged and queued for processing.")
        return PlainTextResponse("Message processed", status_code=200)

    except Exception as e:
        logger.exception("Error processing whatsapp request.")
        # Storage router handles error logging
        raise HTTPException(status_code=500, detail=f"Error processing request: {e!s}")
