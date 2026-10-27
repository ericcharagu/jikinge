import asyncio
import os
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from models import MatchedInventoryItems, ProductRequest
from utils.api.api_base import post_api_request
from utils.api.api_schema import check_and_convert_image_link

from config import WHATSAPP_HEADERS, WHATSAPP_URL, settings
from messages.messages_schema import (
    ButtonsMessage,
    CarouselMessage,
    DocumentMessage,
    FallbackTextMessage,
    ImageMessage,
    InteractiveListMessage,
    InteractiveListRow,
    LocationRequestMessage,
    TextMessage,
    create_media_carousel,
)

from .whatsapp_schema import (
    whatsapp_decryption,
)

# Key: hash of original image path, Value: path to converted image
_image_conversion_cache: dict[str, str] = {}


class WhatsAppMessengerService:
    """WhatsApp messaging service adapter with the different reply methods"""

    def __init__(
        self,
        whatsapp_url: str = WHATSAPP_URL,
        headers: dict[str, str] = WHATSAPP_HEADERS,
        whatsapp_access_token: str = settings.WHATSAPP_ACCESS_TOKEN,
    ):
        self.whatsapp_url: str = whatsapp_url
        self.headers: dict[str, str] = headers
        self.whatsapp_access_token: str = whatsapp_access_token

        self.__post_init__()

    def __post_init__(self):
        """Handle validation of the access token"""
        if not self.whatsapp_access_token:
            raise ValueError("Please provide a WhatsApp token in the .env file")

    @staticmethod
    def _decrypt_user_id(user_id: str) -> str:
        return whatsapp_decryption(user_id)

    @logger.catch
    async def send_whatsapp_text(self, user_id: str, message: TextMessage):
        """Send llm response via whatsapp."""

        payload: dict[str, str | dict[str, Any]] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "recipient": self._decrypt_user_id(user_id),
            "type": "text",
            "text": {
                "body": message.body,
            },
        }
        await post_api_request(self.whatsapp_url, payload=payload, headers=self.headers)

    async def send_interactive_list(self, user_id, message: InteractiveListMessage):
        """Send llm response via interactive lists whatsapp."""
        # Generate the payload to be sent
        payload: dict[str, str | dict[str, Any]] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "recipient": f"{self._decrypt_user_id(user_id)}",
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": message.header},
                "body": {"text": message.body},
                "footer": {"text": message.footer},
                "action": {
                    "button": message.button_text,
                    "sections": [
                        {
                            "title": section_title,
                            "rows": [
                                {
                                    "id": row.row_id,
                                    "title": row.row_title,
                                    "description": row.row_description,
                                }
                                for row in rows
                            ],
                        }
                        for section_title, rows in group_rows_by_section(
                            message.interactive_row_data
                        )
                    ],
                },
            },
        }
        await post_api_request(self.whatsapp_url, payload=payload, headers=self.headers)

    async def send_location_request(
        self, user_id: str, message: LocationRequestMessage
    ):
        """Send llm response via WhatsApp using the default LocationRequestMessage object."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "recipient": f"{self._decrypt_user_id(user_id)}",
            "type": "interactive",
            "interactive": {
                "type": "location_request_message",
                "body": {"text": message.body},
                "action": {"name": "send_location"},
            },
        }

        await post_api_request(self.whatsapp_url, payload=payload, headers=self.headers)

    async def send_images_via_whatsapp(
        self, user_id: str, message: ImageMessage
    ) -> None:
        """Send llm response via whatsapp."""

        try:
            # Clean up old cache files periodically
            cleanup_old_cache(max_age_hours=24, max_files=100)

            # Check and convert image if needed
            processed_image_path: str = check_and_convert_image_link(message.image_link)

            # Upload to cloud and get URL
            if processed_image_path.startswith(
                "/tmp"
            ) or processed_image_path.startswith("media_files"):
                logger.info(f"Uploading local file to Meta: {processed_image_path}")
                media_id = await upload_to_whatsapp(processed_image_path)
                image_payload = {"id": media_id, "caption": message.caption}
            else:
                # It's an existing public URL
                image_payload = {
                    "link": processed_image_path,
                    "caption": message.caption,
                }

            # Prepare the payload
            payload: dict[str, str | dict[str, Any]] = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "recipient": f"{self._decrypt_user_id(user_id)}",
                "type": "image",
                "image": image_payload,
            }

            response = await post_api_request(
                WHATSAPP_URL, payload=payload, headers=self.headers
            )

            # Clean up temporary files if they were created and not cached
            if processed_image_path != message.image_link:
                # Check if this is a cache file (don't delete cache)
                is_cached = any(
                    cache_path == processed_image_path
                    for cache_path in _image_conversion_cache.values()
                )

                if not is_cached:
                    try:
                        Path(processed_image_path).unlink()
                        # Also remove the temporary directory if empty
                        temp_dir = Path(processed_image_path).parent
                        if temp_dir.exists() and not any(temp_dir.iterdir()):
                            temp_dir.rmdir()
                        logger.debug(
                            f"Cleaned up temporary file: {processed_image_path}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to cleanup temporary file {processed_image_path}: {e}"
                        )

            if response.status_code != 200:
                logger.error(
                    f"Failed to send message to {user_id}. Status: {response.status_code} and {response.json()}"
                )
                # Send a fallback text message

                await self.send_whatsapp_text(
                    user_id=user_id,
                    message=FallbackTextMessage(),
                )

        except Exception as e:
            logger.error(f"Failed to send inventory image to {user_id}: {e!s}")
            # Send an error message to the user with the product info
            fallback_message = TextMessage(
                body=f"Sorry, we couldn't process the product image. Product details:\n\n{message.caption}"
            )
            await self.send_whatsapp_text(user_id=user_id, message=fallback_message)

    async def send_interactive_buttons_message(
        self,
        user_id: str,
        message: ButtonsMessage,
    ) -> None:
        buttons = []
        for button in message.buttons:
            buttons.append(
                {"type": button.type, "reply": {"id": button.id, "title": button.title}}
            )

        payload: dict[str, str | dict[str, Any]] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "recipient": f"{self._decrypt_user_id(user_id)}",
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": message.header,
                },
                "body": {"text": message.body},
                "footer": {"text": message.footer},
                "action": {"buttons": buttons},
            },
        }

        await post_api_request(self.whatsapp_url, payload=payload, headers=self.headers)

    async def send_media_carousel(self, user_id: str, message: CarouselMessage):
        # Build the cards array for the payload
        cards_payload = []
        converted_links = await asyncio.gather(
            *(check_and_convert_image_link(card.link) for card in message.cards)
        )
        for card, converted_link in zip(message.cards, converted_links):
            # Base card structure
            card_data: dict[str, Any] = {
                "card_index": card.card_index,
                "type": card.header_type,
            }

            # card.link = await check_and_convert_image_link(image_link=card.link)
            # Add header with media
            card_data["header"] = {
                "type": card.card_type,
                card.card_type: {"link": converted_link},
            }

            # Add body text if present
            if card.text:
                card_data["body"] = {"text": card.text}

            # Add action with buttons
            if card.buttons:
                buttons_list = []
                for button in card.buttons:
                    buttons_list.append(
                        {
                            "type": button.type,
                            "quick_reply": {"id": button.id, "title": button.title},
                        }
                    )

                card_data["action"] = {"buttons": buttons_list}

            cards_payload.append(card_data)

        # Build the complete payload
        payload: dict[str, str | dict[str, Any]] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "recipient": f"{self._decrypt_user_id(user_id)}",
            "type": "interactive",
            "interactive": {
                "type": "carousel",
                "body": {"text": message.text},
                "action": {"cards": cards_payload},
            },
        }

        await post_api_request(self.whatsapp_url, payload=payload, headers=self.headers)

    async def send_document(self, user_id: str, message: DocumentMessage):
        """Send llm response via WhatsApp."""

        payload: dict[str, str | dict[str, Any]] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "recipient": f"{self._decrypt_user_id(user_id)}",
            "type": "document",
            "document": {
                "caption": message.caption,
                "filename": message.file_path,
            },
        }

        await post_api_request(self.whatsapp_url, payload=payload, headers=self.headers)


whatsapp_messenger_service: WhatsAppMessengerService = WhatsAppMessengerService()


def group_rows_by_section(rows: list[InteractiveListRow]):
    """Group rows by section_title_text"""
    sections_dict = defaultdict(list)
    for row in rows:
        sections_dict[row.section_title_text].append(row)
    return sections_dict.items()


def cleanup_old_cache(max_age_hours: int = 24, max_files: int = 100):
    """
    Clean up old cache files to prevent disk space issues.

    Args:
        max_age_hours: Maximum age of cache files in hours
        max_files: Maximum number of files to keep
    """
    try:
        cache_dir = Path(tempfile.gettempdir()) / "image_conversion_cache"
        if not cache_dir.exists():
            return

        files = list(cache_dir.glob("*.jpg"))

        # Sort by modification time (oldest first)
        files.sort(key=lambda x: x.stat().st_mtime)

        # Remove files older than max_age_hours
        current_time = datetime.now().timestamp()
        for file in files:
            file_age_hours = (current_time - file.stat().st_mtime) / 3600
            if file_age_hours > max_age_hours:
                try:
                    file.unlink()
                    logger.debug(f"Removed old cache file: {file}")
                except Exception as e:
                    logger.warning(f"Failed to remove old cache file {file}: {e}")

        # If still too many files, remove oldest
        files = list(cache_dir.glob("*.jpg"))
        if len(files) > max_files:
            files.sort(key=lambda x: x.stat().st_mtime)
            for file in files[: len(files) - max_files]:
                try:
                    file.unlink()
                    logger.debug(f"Removed excess cache file: {file}")
                except Exception as e:
                    logger.warning(f"Failed to remove excess cache file {file}: {e}")

    except Exception as e:
        logger.warning(f"Failed to clean up cache: {e}")


async def upload_to_whatsapp(file_path: str) -> str:
    """
    Uploads a local file to Meta's servers and returns a media_id.
    """
    url = f"https://graph.facebook.com/{settings.API_VERSION}/{settings.PHONE_NUMBER_ID}/media"
    headers_upload = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"}

    async with httpx.AsyncClient() as client:
        with open(file_path, "rb") as f:
            files = {
                "file": (os.path.basename(file_path), f, "image/jpeg"),
                "messaging_product": (None, "whatsapp"),
            }
            response = await client.post(url, headers=headers_upload, files=files)
            response.raise_for_status()
            return response.json().get("id")


async def send_inventory_as_carousel(
    user_id: str,
    product_requests: list[ProductRequest],
    ranked_inventory_list: list[MatchedInventoryItems],
) -> None:
    """
    Processes nested options and maintains a global counter across multiple products.
    """

    media_carousel_metadata: CarouselMessage = create_media_carousel(
        ranked_inventory_list=ranked_inventory_list, product_requests=product_requests
    )
    await whatsapp_messenger_service.send_media_carousel(
        user_id=user_id, message=media_carousel_metadata
    )


# used for testing
# send_whatsapp_text("This is the test for lane", "254736391323")
