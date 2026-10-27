from enum import StrEnum
from typing import Any, Protocol

from excepts import MissingSenderException, UnsupportedMessageTypeException
from loguru import logger

from config import settings
from messages.messages_schema import (
    BaseMessage,
    ButtonsMessage,
    CarouselMessage,
    DocumentMessage,
    ImageMessage,
    InteractiveListMessage,
    LocationRequestMessage,
    TextMessage,
)

from .api.api_base import post_api_request
from .whatsapp.whatsapp_service import (
    whatsapp_messenger_service,
)


class PLATFORM(StrEnum):
    WEB = "web"
    WHATSAPP = "whatsapp"


class MessageSender(Protocol):
    async def send(self, user_id: str, message: BaseMessage) -> None: ...
    async def send_all(
        self,
        user_id: str,
        messages: list[BaseMessage],
    ) -> None:
        for message in messages:
            await self.send(user_id, message)


class WhatsAppSender(MessageSender):
    """Wrapper for WhatsApp services"""

    service = whatsapp_messenger_service

    async def send(self, user_id: str, message: BaseMessage) -> None:
        match message:
            case TextMessage():
                await self.service.send_whatsapp_text(user_id, message)
            case ImageMessage():
                await self.service.send_images_via_whatsapp(user_id, message)
            case DocumentMessage():
                await self.service.send_document(user_id, message)
            case ButtonsMessage():
                await self.service.send_interactive_buttons_message(user_id, message)
            case CarouselMessage():
                await self.service.send_media_carousel(user_id, message)
            case InteractiveListMessage():
                await self.service.send_interactive_list(user_id, message)
            case LocationRequestMessage():
                await self.service.send_location_request(user_id, message)
            case _:
                raise UnsupportedMessageTypeException(
                    message_type=message.type.value, platform="whatsapp"
                )


class WebSender(MessageSender):
    async def send(self, user_id: str, message: BaseMessage) -> None:
        header = {"Accept": "application/json", "Content-type": "application/json"}
        payload: dict[str, str | Any] = {
            "header": header,
            "conversation_id": user_id,
            "data": message.model_dump(),
        }
        logger.info(f"The payload is {payload}")
        await post_api_request(settings.WEB_API_CHAT, payload=payload)


class SenderServivce:
    def __init__(self):
        self._sender_registry: dict[str, MessageSender] = {}

    def register(self, platform: PLATFORM, sender: MessageSender) -> None:
        self._sender_registry[platform] = sender

    def get(self, platform: PLATFORM) -> MessageSender:
        sender = self._sender_registry.get(platform)
        if not sender:
            raise MissingSenderException(platform)
        return sender


# Create and register all sending services
sender: SenderServivce = SenderServivce()
sender.register(platform=PLATFORM.WHATSAPP, sender=WhatsAppSender())
sender.register(platform=PLATFORM.WEB, sender=WebSender())
