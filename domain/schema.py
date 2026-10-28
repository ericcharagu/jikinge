from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, TypedDict

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from config import settings


class LlmMessageType(StrEnum):
    """Enum of the different types of llm messages produced"""

    GREETING = "greeting"
    PRODUCT_RECOMMENDATION = "product_recommendation"
    CART = "cart"
    OOS = "oos"
    CAR_MAINTENANCE = "car_maintenance"
    FAQ = "faq"
    HISTORY = "history"
    ERROR_MESSAGE = "error_message"


class QueryTypeEnum(StrEnum):
    WHATSAPP = "whatsapp"
    WEB = "web"


def _get_llm_instructions_for(query_type: QueryTypeEnum):
    """Map the query with its llm formatter instructions"""
    match query_type:
        case QueryTypeEnum.WHATSAPP:
            return """ *RESPONSE GUIDELINES*
        * Keep responses under *800 words* total
        * Use *bullet points* to break down steps, tiers, or brand features for easy scanning
        * Explain concepts in *simple, jargon-free language* suitable for non-technical users
        * Be *polite, patient, and verbose* enough to fully answer, but avoid unnecessary repetition
        * If the user's request is unclear, ask one concise clarifying question before answering

       *WHATSAPP FORMATTING RULES – STRICT ENFORCEMENT*
        To make text bold on WhatsApp, wrap *only letters A-Z and a-z* with single asterisks.
        Do *not* include numbers, symbols, spaces, or punctuation inside the asterisks.
        use \n\n to start a new line 
        For bullets when listing, use the symbol -. Do NOT use *
        
        Valid examples:
        *Join the jikinge Referral Program* to earn bonuses
        *Return Window* is two days from delivery
        *Refund Process* completes within seven business days

        Invalid examples:
        *Refund Process:* ← colon inside asterisks
        *2 days* ← number inside asterisks
        *7 business days* ← number and space inside asterisks
        *M-Pesa (Paybill)* ← parentheses and space inside asterisks

        For multi-word terms with symbols or numbers, bold only the letters:
        *M-Pesa* Paybill ← bold just the M and Pesa letters
        *KES* 300 delivery fee ← bold just the currency code

        Use *empty lines* between distinct topics to create visible separation on WhatsApp. Avoid markdown headers, code blocks, or horizontal rules – keep formatting plain and WhatsApp-compatible.
    """

        case QueryTypeEnum.WEB:
            return """Format for web interface."""


# ===========================================

# USER MODELS AND HELPER FUNCTIONS

# ===========================================


class InsuranceTypes(StrEnum):
    MOTOR = "motor"
    HEALTH = "health"
    HOME = "home"


class DeductibleType(StrEnum):
    DISCOUNT = "discount"
    LEVIES = "levies"


class Deductible(TypedDict):
    deductible_type: DeductibleType
    deductible_name: str
    deductible_value: str


class Premium(TypedDict):
    premium_name: str
    premium_value: str


class VehicleMetadata(BaseModel):
    vehicle_registration: str = Field(default="")
    vehicle_make: str = Field(
        default="",
        description="Customer's vehicle make(s) - e.g.'Toyota'or 'Honda'. Helps recommend compatible parts. Ask 'What car do you drive?' - critical for fitment!",
    )
    vehicle_year_of_manufacture: str = Field(default="")


class User(BaseModel):
    """
    User object to maintain state across conversations.

    This is the PRIMARY customer record for the conversation session.
    Check this first when a customer returns to see their cart, preferences,
    and previous interactions.
    """

    user_name: str = Field(defaul="", description="Name of the user")
    user_id: str = Field(
        default="",
        description="User's unique id from their request source.",
    )
    insurance_type: InsuranceTypes = Field(
        default=InsuranceTypes.MOTOR, description="Type of insurance the user wants"
    )
    metadata: Any = Field(
        default=VehicleMetadata, description="Details of the object being insured"
    )
    sum_insured: str = Field(default="")
    base_rate_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    premiums: list[Premium] = Field(default_factory=list)
    deductibles: list[Deductible] = Field(default_factory=list)
    total_payable: str = Field(
        default="",
        description="Amount user has to pay after deductibles from the base premium",
    )

    @property
    def insurance_sum(self) -> Decimal:
        """Insurance sum to be paid based on object value"""
        return Decimal(self._sum_insured)

    @property
    def gross_base(self) -> Decimal:
        """Initial amount payable before the deductibles"""
        return Decimal(str(self._sum_insured * self.base_rate))

    @property
    def gross_base_premium(self) -> str:
        """Calculate the initial premium to be paid"""
        gross_base_premium = Decimal(self._sum_insured) * Decimal(
            str(self._base_rate_percentage)
        ) + sum([Decimal(premium.premium_value) for premium in self.premiums])

        return str(gross_base_premium)

    def calculate_total_payable(self, initial_total_payable: str) -> str:
        """Calculate the amount to be paid after the deductibles"""
        total_payable: Decimal = Decimal(initial_total_payable)
        for deductible in self.deductibles:
            if "%" in deductible.deductible_value:
                total_payable -= total_payable * Decimal(deductible.deductible_value)
            total_payable - Decimal(deductible.deductible_value)
        return str(total_payable)

    # Helpful methods for data access and setting
    # ===== CONFIGURATION =====
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        # Validate default values on model creation
        validate_default=True,
        # Don't allow extra fields (prevents data corruption)
        extra="forbid",
        # Strip whitespace from strings (clean phone numbers, etc.)
        str_strip_whitespace=True,
        # Protect against attribute modification attacks
        validate_assignment=True,
        # Add example for API documentation
        json_schema_extra={
            "example": {
                "user_id": "kajhsdhaos",
                "user_name": "John Doe",
                "insurance_type": "InsuranceTypes.MOTOR",
                "metadata": {
                    "vehicle_registration": "KAA 000A",
                    "vehicle_make": "Toyota",
                    "vehicle_year_of_manufacture": "2000",
                },
                "_sum_insured": "1,000,000",
                "base_rate": 4.0,
                "total_payable": "100,000",
            }
        },
    )

    # ===== VALIDATORS =====
    @model_validator(mode="after")
    def validate_session_dates(self) -> User:
        """Ensure timestamps are logical"""
        # Check that expires_at is after created_at
        created = datetime.fromisoformat(self.created_at)
        expires = datetime.fromisoformat(self.expires_at)

        if expires <= created:
            # Auto-correct if invalid
            self.expires_at = (created + timedelta(days=30)).isoformat()

        return self


# ==================

# CACHE CLASS

# ==================


class CacheMessage(BaseModel):
    """
    Cached conversation message for tracking customer interactions.

    This stores EVERY message exchange between customer and agent/LLM.
    Use this to:
    - Review conversation history when customer calls back
    - Track what products customer asked about previously
    - Debug issues with LLM responses
    - Analyze customer sentiment and intent patterns
    """

    user_message_timestamp: str = Field(
        default_factory=lambda: datetime.now(settings.NAIROBI_TZ).isoformat(),
        description="When the customer sent their message. Use to track response times and conversation flow.",
    )

    user_message: str = Field(
        default="",
        max_length=5000,
        description="The customer's original message VERBATIM. NEVER paraphrase or summarize - exact wording helps with legal compliance and intent analysis.",
    )

    llm_response: str = Field(
        default="",
        max_length=10000,
        description="The LLM's or agent's response to the customer. Review if customer complains about incorrect information.",
    )

    llm_message_type: LlmMessageType = Field(
        default=..., description="Type of message from the LLM"
    )

    intent: str = Field(
        default="",
        description="Detected customer intent (e.g., 'product_inquiry', 'price_check', 'complaint', 'order_status', 'return_request'). Use to categorize and prioritize responses.",
    )

    user: User = Field(
        default_factory=User,
        description="Customer user object at time of message. Captures cart state, car make, address - complete snapshot of customer context.",
    )

    timings: list[dict[str, float]] = Field(
        default_factory=list,
        description="Performance tracking data: [{ 'llm_latency': 1.23, 'cart_load_time': 0.45, 'response_generation': 0.89 }]. Use for debugging slow responses.",
    )

    # ===== CONFIGURATION =====
    model_config = ConfigDict(
        # Allow User type (custom class)
        arbitrary_types_allowed=True,
        # Validate defaults
        validate_default=True,
        # Prevent extra fields (data integrity)
        extra="forbid",
        # Strip whitespace from strings
        str_strip_whitespace=True,
        # Add JSON schema examples for API docs
        json_schema_extra={
            "examples": [
                {
                    "user_message_timestamp": "2024-01-15T10:30:00",
                    "user_message": "I need a battery for my Toyota Hilux",
                    "llm_response": "I can help with that! What year is your Hilux?",
                    "intent": "product_inquiry",
                    "cart_id": "cart_ABC123_456",
                    "timings": [{"llm_latency": 0.85, "total_time": 1.2}],
                },
                {
                    "user_message_timestamp": "2024-01-15T10:35:00",
                    "user_message": "2019 model",
                    "llm_response": "Perfect! We have a premium battery for 2019 Hilux at ₦45,000",
                    "intent": "specification_provided",
                    "cart_id": "cart_ABC123_456",
                },
            ],
            "description": "Complete message history record - essential for customer service continuity",
        },
    )


class InterventionError(BaseModel):
    """Defines how to describe when human intervention is required"""

    flag_reason: str = Field(..., description="Reason for flagging the intervention")
    error_type: str = Field(
        default_="",
        description="Type of error that occurred",
    )
    detection_time: datetime = Field(..., description="When the error was detected")
    additional_notes: str = Field(
        default="", description="Additional context about the error"
    )

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        json_schema_extra={
            "example": {
                "flag_reason": "Invalide address",
                "error_type": "validation_error",
                "detection_time": "2024-12-27 08:26:49.219717",
                "additional_notes": " ",
            }
        },
    )
