import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Any

from config import USER_SESSION_TTL, settings
from domain.excepts import NoProcessableMessageException, WhatsAppMessageTypeException
from domain.schema import User

from .whatsapp_schema import MessageRequest


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify the X-Hub-Signature-256 header matches the payload signature"""
    if not settings.REQUEST_TOKEN:
        return True

    expected_signature = hmac.new(
        key=settings.REQUEST_TOKEN.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)


def create_user_from_request(user_id: str) -> User:
    """Create a new user object from request data"""
    cart_id = f"cart_{user_id}_{int(datetime.now(settings.NAIROBI_TZ).timestamp())}"
    current_time = datetime.now(settings.NAIROBI_TZ).isoformat()
    expires_at = (
        datetime.now(settings.NAIROBI_TZ) + timedelta(seconds=USER_SESSION_TTL)
    ).isoformat()

    return User(
        user_id=user_id,
        address="unknown",
        created_at=current_time,
        updated_at=current_time,
        expires_at=expires_at,
    )


def extract_request_from_whatsapp(
    message_request: MessageRequest, whatsapp_message: dict[str, Any]
) -> MessageRequest:
    for entry in whatsapp_message.get("entry", []):
        for change in entry.get("changes", []):
            # Extract the contact info
            contact_info = change.get("value", {}).get("contacts", [])
            if contact_info:
                message_request.user_number = contact_info[0]["user_id"]
                message_request.user_name = (
                    contact_info[0]["profile"]["name"]
                    if contact_info[0]["profile"]["name"]
                    else contact_info[0]["profile"]["username"]
                )
            # Get the message timestamp
            message_status = change.get("value", {}).get("statuses", {})
            if message_status:
                message_timestamp_string = message_status[0].get("timestamp")
                message_request.user_message_timestamp = datetime.fromtimestamp(
                    int(message_timestamp_string)
                )

            messages = change.get("value", {}).get("messages", [])

            # Get the whatsapp message id and remove the default prefix
            message_request.whatsapp_message_id = messages[0].get("id").split(".")[1]

            # Get the actual message for a simple message
            message_type = messages[0].get("type")
            message_request: MessageRequest = extract_details_from_message_type(
                message_type=message_type,
                messages=messages,
                message_request=message_request,
            )

        break

    return message_request


def extract_details_from_message_type(
    message_type: str, messages: list[dict[str, Any]], message_request: MessageRequest
) -> MessageRequest:
    """Extract the user's input from different media types from WhatsApp

    Args:
        message_type (str): The type of message from whatsapp e.g text, image, interactive
        messages (list[dict[str, Any]]): the actual payload received from the API
        message_request (MessageRequest): Domain data type for interacting with whatsapp data type

    Raises:
        WhatsAppMessageTypeException: Raised when a message type is received without the appropriate handler function

    Returns:
        MessageRequest: Domain data type for interacting with whatsapp data type

    """
    match message_type:
        case "interactive":
            if (
                messages[0]["interactive"]["type"] == "list_reply"
            ):  # Response from interactive list selection
                message_request.user_message = (
                    messages[0]["interactive"]
                    .get("list_reply", {})
                    .get("id")
                    .replace(" ", "")
                )

            if (
                messages[0]["interactive"]["type"] == "button_reply"
            ):  # Response from interactive reply buttons
                message_request.user_message = (
                    messages[0]["interactive"]
                    .get("button_reply", {})
                    .get("id")
                    .replace(" ", "")
                )

            return message_request

        case "location":
            message_request.latitude = (
                messages[0].get("location", {}).get("latitude", "")
            )
            message_request.longitude = (
                messages[0].get("location", {}).get("longitude", "")
            )
            message_request.address_id = messages[0].get("id", "")

            return message_request
        case "text":
            message_request.user_message = messages[0].get("text", {}).get("body")
            return message_request
        case "image":
            message_request.media_id = messages[0].get("image", {}).get("id")
            message_request.image_caption = (
                messages[0].get("image", {}).get("caption", "")
            )
            return message_request
        case "button":  # Response from media carousel
            message_request.user_message = messages[0]["button"].get("payload", "")
            return message_request

        case _:
            raise WhatsAppMessageTypeException(message_type)


def extract_message_details(
    whatsapp_message: dict[str, Any],
    message_request: MessageRequest = MessageRequest(),
) -> MessageRequest:
    """Extract and parse message details from WhatsApp payload"""

    value = whatsapp_message["entry"][0]["changes"][0].get("value", {})
    if not value:
        raise NoProcessableMessageException("Empty value node in webhook payload")
    if "statuses" in value:
        raise NoProcessableMessageException("Empty value node in webhook payload")

    return extract_request_from_whatsapp(message_request, whatsapp_message)
