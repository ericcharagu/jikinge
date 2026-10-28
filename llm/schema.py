from typing import Any, Self

from pydantic import BaseModel, Field, field_validator

from domain.messages_schema import TextMessage
from domain.schema import CacheMessage, LlmMessageType, User


class PlannerAgentInput(BaseModel):
    """Input data model for the planner agent processing pipeline"""

    user_message: str = Field(
        default="",
        description="The raw text message sent by the user that needs to be processed and responded to",
    )

    chat_history: list[CacheMessage] = Field(
        default_factory=list,
        description="List of previous conversation messages between the user and the bot, used for maintaining context and continuity",
    )
    intent_metadata: dict[str, Any] = Field(
        default_factory=dict[str, Any],
        description="A summary of the user's intentions from the query",
    )
    user: User = Field(
        ...,
        description="The current user object containing profile information, preferences, and session data",
    )

    request: Any = Field(
        default=None,
        description="FastAPI request object containing HTTP request metadata, headers, and context (optional)",
    )

    @property
    def user_id(self) -> str:
        return self.user.user_id

    @property
    def price_range(self) -> str:
        return self.intent_metadata.get("order_details", {}).get("price", "")


class PlannerAgentOutput(BaseModel):
    """Output data model from the planner agent processing pipeline"""

    messages: list[Any] = Field(default_factory=list)

    response_text: str = Field(
        default="",
        description="The generated response text to be sent back to the user based on their query and intent",
    )
    llm_message_type: LlmMessageType = Field(
        default=..., description="Previous LLM message type"
    )
    updated_user_object: User | None = Field(
        default=None,
        description="Updated user object containing any modifications made during the conversation (e.g., preferences, referral code, order context). Returns None if no updates were made",
    )

    timings: list[dict[str, float]] = Field(
        default_factory=list,
        description="List of timing measurements for different processing stages in the pipeline, each dict containing stage names and their execution durations in seconds",
    )

    intent_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about the classified user intent including intent type, confidence scores, extracted entities, and contextual flags like 'requires_chat_context' and 'order_details'",
    )

    def _combined_output_generator(self) -> Self:
        # Convert the response into a generic text type
        response_text_message = TextMessage(body=self.response_text)

        # Append the new text message to the existing message list
        self.messages.append(response_text_message)
        return self

    def _serialize_payload(self) -> list[dict[str, Any]]:
        # Update the messages list
        self._combined_output_generator()
        return [message.model_dump() for message in self.messages]


class HandlerResult(BaseModel):
    """Defines the output of all intention handlers"""

    messages: list[Any] = Field(default_factory=list)
    response_content: dict[str, Any] | str | None = Field(
        default="",
        description="Additional context provided outside the main output type",
    )
    llm_message_type: LlmMessageType = Field(
        default=...,
        description="Indicates the llm message response type based on the intent",
    )
    updated_user: User | None = Field(
        default_factory=User, description="The current user's details"
    )
    timings: float | Any = Field(
        default=0.0,
        description="Stores how long each function/agent took to fulfil a request",
    )

    @field_validator("timings", mode="before")
    @classmethod
    def handle_none_timings(cls, v: Any) -> float | Any:
        """Replaces your __post_init__ logic to catch None values gracefully"""
        if v is None:
            return []
        return v
