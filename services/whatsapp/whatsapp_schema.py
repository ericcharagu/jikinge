from config import settings
from pathlib import Path
import base64
from datetime import datetime
from enum import StrEnum

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from pydantic import BaseModel, ConfigDict, Field


class WhatsappResponseType(StrEnum):
    TEXT = "text"
    IMAGES = "images"
    INTERACTIVE_LIST = "interactive_list"
    INTERACTIVE_BUTTON = "interactive_button"
    MEDIA_CAROUSEL = "media_carousel"


class InteractiveRowObject(BaseModel):
    row_id: str = Field(default="", max_length=200)
    section_title_text: str = Field(
        default="",
        max_length=24,
        description="Title for each row of the modal. For example the tyre specification i.e 255/65r17",
    )
    row_title: str = Field(
        default="",
        max_length=24,
        description="Title for each item in the section. For example of brands under each specification e.g 'Laufenn 225/50r17'",
    )
    row_description: str = Field(default="", max_length=72)


class WhatsAppInteractiveList(BaseModel):
    message_header: str = Field(default="", max_length=60, description="")
    message_body: str = Field(default="", max_length=4096, description="")
    message_footer: str = Field(default="", max_length=60, description="")
    button_text: str = Field(default="", max_length=20, description="")
    interactive_row_data: list[InteractiveRowObject] = Field(
        default_factory=list
    )  # A max of 10 combined rows for a max of 10 sections

    model_config = ConfigDict(arbitrary_types_allowed=True)


def whatsapp_encryption(user_id: bytes) -> str:
    """Encode the whatsapp phone number"""
    # 1. Set up AES cipher in ECB mode
    cipher = AES.new(settings.WHATSAPP_FERNET_KEY.encode("utf-8"), AES.MODE_ECB)

    # 2. Pad the text to match AES block size (16 bytes) and encrypt
    padded_data = pad(user_id, AES.block_size)
    encrypted_bytes = cipher.encrypt(padded_data)

    # 3. Encode to Base64 bytes
    return base64.b64encode(encrypted_bytes).decode("utf-8")


def whatsapp_decryption(user_id: str) -> str:
    """Dencode the whatsapp phone number"""

    cipher = AES.new(settings.WHATSAPP_FERNET_KEY.encode("utf-8"), AES.MODE_ECB)

    # Decode from Base64 (not encode to UTF-8!)
    encrypted_bytes = base64.b64decode(user_id)

    decrypted_padded = cipher.decrypt(encrypted_bytes)

    # Remove padding and decode back to string
    return unpad(decrypted_padded, AES.block_size).decode("utf-8")


class MessageRequest(BaseModel):
    """Request details from the whatsapp message"""

    user_message: str = Field(
        default="",
        description="The text content of the message sent by the user via WhatsApp",
    )
    user_name: str = Field(
        default="", description="The display name of the user as registered on WhatsApp"
    )
    user_message_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(settings.NAIROBI_TZ),
        description="Timestamp when the message was received from the user, using Nairobi timezone (EAT)",
    )
    whatsapp_message_id: str = Field(
        default="",
        description="Unique identifier for the message assigned by WhatsApp's messaging API",
    )
    conversation_id: str = Field(
        default="",
        description="Unique identifier for the conversation thread between the user and the bot",
    )
    user_number: str = Field(
        default="",
        description="The phone number of the user in international format (e.g., 2547XXXXXXXX)",
    )
    address_id: str = Field(
        default="",
        description="Unique identifier for the user's registered delivery address in the system",
    )
    media_id: str = Field(
        default="",
        description="Unique identifier for any media attachment (image, video, document) sent with the message",
    )
    image_caption: str = Field(
        default="",
        description="Caption text associated with an image media attachment in the message",
    )
    latitude: str = Field(
        default="",
        description="Latitude coordinate extracted from shared location messages (in decimal degrees format)",
    )
    longitude: str = Field(
        default="",
        description="Longitude coordinate extracted from shared location messages (in decimal degrees format)",
    )

    @property
    def user_id(self) -> str:
        """Encrypt the user's phone number for privacy"""
        encoded_user_id: bytes = self.user_number.encode("utf-8")
        return whatsapp_encryption(encoded_user_id)


class InteractiveButton(BaseModel):
    type: str = Field(
        default="reply", description="The type of button expected by whatsapp."
    )
    id: str = Field(
        default="",
        min_length=1,
        max_length=256,
        description="Message received on reply by user",
    )
    title: str = Field(
        default="",
        min_length=1,
        max_length=20,
        description="Message displayed by the user",
    )


class MessageWithInteractiveReplyButtons(BaseModel):
    message_header: str = Field(default="", description="Introduction to the message")
    body: str = Field(
        default="",
        min_length=1,
        max_length=1024,
        description="Actual body of the message",
    )
    footer_text: str = Field(
        default="",
        description="Text at the bottom of the message before the interactive buttons",
    )
    buttons: list[InteractiveButton] = Field(
        default_factory=list, description="List of interactive buttons"
    )
