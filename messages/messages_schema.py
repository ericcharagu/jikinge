from enum import StrEnum
from pathlib import Path
from typing import Any

from models import MatchedInventoryItems, ProductRequest
from pydantic import BaseModel, Field

from config import settings


class MessageType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    CAROUSEL = "carousel"
    INTERACTIVE_LIST = "interactive_list"
    BUTTONS = "buttons"
    LOCATION_REQUEST = "location_request"


class BaseMessage(BaseModel):
    """Base class of response types"""

    type: MessageType
    metadata: dict[str, Any] = Field(default_factory=dict)


class TextMessage(BaseMessage):
    """Only alphanumeric characters in the body"""

    type: MessageType = MessageType.TEXT
    body: str


class FallbackTextMessage(BaseMessage):
    """Default response to the user when internal system is down"""

    type: MessageType = MessageType.TEXT
    body: str = f"Hi Cousin😀.Jikinge is currently on a break. Please give it a moment or call us on {settings.HUMAN_INTERVENTION_NUMBER} for assistance.\n\nThank you for your understanding!"


class ImageMessage(BaseMessage):
    """Image object"""

    type: MessageType = MessageType.IMAGE
    image_link: str
    caption: str = ""


class DocumentMessage(BaseMessage):
    type: MessageType = MessageType.DOCUMENT
    file_path: Path
    caption: str


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


class ButtonsMessage(BaseMessage):
    type: MessageType = MessageType.BUTTONS
    header: str = ""
    body: str = ""
    footer: str = ""
    buttons: list[InteractiveButton]


class LocationRequestMessage(BaseMessage):
    type: MessageType = MessageType.LOCATION_REQUEST
    body: str = Field(
        default="Awesome! We just need to know where to deliver.\nPlease provide your address.\n"
    )


class CarouselCard(BaseModel):
    card_index: int = Field(
        default=0,
        le=settings.MAX_ALLOWED_CAROUSEL_CARD_INDEX,
        description="Card position in the Carousel. Maximum of 10",
    )
    header_type: str = Field(
        default="cta_url",
        description="Header used to identify the type of media type expected by Meta",
    )

    card_type: str = Field(
        default="image",
        description="Card type used to identify the type of media type expected by Meta",
    )
    link: str = Field(
        default="",
        description="Link to the image to be used. WhatsApp requires a link from a hosted source",
    )
    text: str = Field(default="", description="Details of the card")
    buttons: list[InteractiveButton] = Field(
        default_factory=list,
        description="The interactive buttons used for the call to action",
    )


class CarouselMessage(BaseModel):
    """Structure of the payload used in the carousel"""

    text: str = Field(
        default="Here are the options available. Ranked in order from the best.",
        description="Main message text",
    )
    cards: list[CarouselCard] = Field(default_factory=list, description="")


class InteractiveListRow(BaseModel):
    """Represents the content of the interactive list"""

    row_id: str
    row_title: str
    row_description: str
    section_title_text: str


class InteractiveListMessage(BaseMessage):
    """Represents the entire interactive message payload"""

    type: MessageType = MessageType.INTERACTIVE_LIST
    header: str = ""
    body: str = ""
    footer: str = ""
    button_text: str = "Please select an option."
    interactive_row_data: list[InteractiveListRow]


def _generate_media_carousel_metadata(
    index: int, item_image_link: str, caption: str
) -> CarouselCard:
    """Generate the metadata object used by Meta's media carousel API"""
    buttons = [
        InteractiveButton(
            type="quick_reply",
            id=f"learn_more_about_{caption}",
            title="Learn More",
        ),
    ]
    return CarouselCard(
        card_index=index,
        link=item_image_link,
        text=caption,
        buttons=buttons,
    )


def generate_caption() -> str:
    return "Caption for any document"


def create_media_carousel(
    ranked_inventory_list: list[MatchedInventoryItems],
    product_requests: list[ProductRequest],
) -> CarouselMessage:
    global_option_idx = 1

    card_carousel_list: list[CarouselCard] = []
    card_index: int = 0
    # Iterate through each requested product and its corresponding matches
    for req, sub_list in zip(product_requests, ranked_inventory_list):
        if not sub_list:
            continue

        if not isinstance(sub_list, list):
            sub_list = [sub_list]

        for item in sub_list:
            if not item.product_image:
                item.product_image = settings.FALLBACK_PRODUCT_IMAGE

            caption = generate_caption()
            if card_index >= settings.MAX_ALLOWED_CAROUSEL_CARD_INDEX:
                break
            card_metadata: CarouselCard = _generate_media_carousel_metadata(
                index=card_index,
                item_image_link=item.product_image,
                caption=caption,
            )
            card_carousel_list.append(card_metadata)
            card_index += 1
            global_option_idx += 1
    return CarouselMessage(cards=card_carousel_list)
