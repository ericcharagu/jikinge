from datetime import datetime
from enum import StrEnum
from typing import Any

from utils.messaging.messages_schema import FallbackTextMessage

from config import settings


class SystemErrorType(StrEnum):
    """Enum of the different error types in the application"""

    REGISTRY_ERROR = "registry_error"  # Missing intent handler
    RUNTIME_EXCEPTION = (
        "runtime_exception"  # Logic/Python crashes (e.g., Subscripting error)
    )
    LLM_FAILURE = "llm_failure"  # Model timeout or malformed JSON
    DATABASE_ERROR = "database_error"  # Postgres down
    QUEUE_ERROR = "queue_error"  # Queue manager error
    CACHE_ERROR = "cache_error"  # Redis or cache database is down
    VECTOR_DB_ERROR = "vector_db_error"  # Qdrant or Embedding server failure
    API_FAILURE = "api_failure"  # Lane API 500s or timeouts
    MEDIA_ERROR = "media_error"  # WhatsApp Image download failure
    VALIDATION_ERROR = "validation_error"  # Critical data corruption


class ErrorSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class JikingeAgentException(Exception):
    """Base exception for Lane related errors"""

    severity: ErrorSeverity = ErrorSeverity.MEDIUM

    def __init__(
        self,
        message: str,
        user_friendly_message: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        self.message: str = message
        if user_friendly_message:
            self.user_friendly_message: str = user_friendly_message
        else:
            self.user_friendly_message = FallbackTextMessage().body
        self.context: dict[str, Any] = context or {}
        super().__init__(message)


class MissingIntentHandlerError(JikingeAgentException):
    """Raised when an intention has no handler to process the request"""

    severity: ErrorSeverity = ErrorSeverity.HIGH

    def __init__(self, intent) -> None:

        super().__init__(
            message="Cannot find handler for the user's intent",
            context={"intent": intent},
        )


class MissingSenderException(JikingeAgentException):
    """Raised when a platform has no sender"""

    severity: ErrorSeverity = ErrorSeverity.HIGH

    def __init__(self, platform: str) -> None:

        super().__init__(
            message=f"Cannot find a sender for {platform}",
            context={"platform": platform},
        )


class MediaDownloadException(JikingeAgentException):
    """Exception for media download failures"""

    severity: ErrorSeverity = ErrorSeverity.HIGH

    def __init__(self, media_id: str, original_error: Exception):
        super().__init__(
            message=f"Failed to download media {media_id}: {original_error!s}",
            context={"media_id": media_id},
        )


class DatabaseConnectionStringException(JikingeAgentException):
    """Exception raised when constructing the persistant database connection string for the async engine"""

    severity: ErrorSeverity = ErrorSeverity.HIGH

    def __init__(self, media_id: str, original_error: Exception):
        super().__init__(
            message="Cannot generate the database connection string",
        )


class EmptyCacheClientException(JikingeAgentException):
    severity: ErrorSeverity = ErrorSeverity.HIGH

    def __init__(self):
        super().__init__(
            message="Client Cache is None",
            context={"timestamp": datetime.now(settings.NAIROBI_TZ).isoformat()},
        )


class NoQueueManagerException(JikingeAgentException):
    severity: ErrorSeverity = ErrorSeverity.HIGH

    def __init__(self):
        super().__init__(
            message="Queue Manager is None",
            context={"timestamp": datetime.now(settings.NAIROBI_TZ).isoformat()},
        )


class UserSessionException(JikingeAgentException):
    """Exception for user session issues"""

    severity: ErrorSeverity = ErrorSeverity.MEDIUM

    def __init__(self, user_id: str, original_error: Exception):
        super().__init__(
            message=f"User session error for {user_id}: {original_error!s}",
            context={"user_id": user_id},
        )


class WebhookProcessingException(JikingeAgentException):
    """Exception for webhook processing"""

    severity: ErrorSeverity = ErrorSeverity.HIGH

    def __init__(self, platform: str, original_error: Exception):
        super().__init__(
            message=f"Webhook processing error on {platform} platform: {original_error!s}",
        )


class ProfileCreationException(JikingeAgentException):
    """Exception for creating user profile"""

    severity: ErrorSeverity = ErrorSeverity.HIGH

    def __init__(self, user_id: str, original_error: Exception):
        super().__init__(
            message=f"Cannot create a profile for {user_id}: {original_error!s}",
            context={"user_id": user_id},
        )


class LlmProcessingException(JikingeAgentException):
    """Exception for LLM/Agent processing failures"""

    severity: ErrorSeverity = ErrorSeverity.HIGH

    def __init__(self, original_error: Exception, user_message: str = ""):
        super().__init__(
            message=f"LLM processing failed: {original_error!s}",
            context={"user_message": user_message},
        )


class WhatsAppAPIException(JikingeAgentException):
    """Exception for WhatsApp API failures"""

    severity: ErrorSeverity = ErrorSeverity.CRITICAL

    def __init__(self, original_error: Exception, user_id: str):
        super().__init__(
            message=f"WhatsApp API failure for {user_id}: {original_error!s}",
            context={"user_id": user_id},
        )


class WhatsAppMessageTypeException(JikingeAgentException):
    """Exception for WhatsApp API message processing failures"""

    severity: ErrorSeverity = ErrorSeverity.LOW

    def __init__(self, message_type: str):
        super().__init__(
            message=f"Cannot process the message type {message_type}",
        )


class CacheOperationException(JikingeAgentException):
    """Exception for cache operations"""

    severity: ErrorSeverity = ErrorSeverity.HIGH

    def __init__(self, operation: str, key: str | None, original_error: Exception):
        super().__init__(
            message=f"Cache {operation} failed for {key}: {original_error!s}",
            context={"operation": operation, "key": key},
        )


class UnsupportedMessageTypeException(JikingeAgentException):
    severity: ErrorSeverity = ErrorSeverity.MEDIUM

    def __init__(self, message_type: str, platform: str):
        super().__init__(
            message=f"Failed to process message type {message_type} on the platform {platform}",
        )


class InterventionMessageDeliveryException(JikingeAgentException):
    severity: ErrorSeverity = ErrorSeverity.HIGH

    def __init__(self, intervention_error_message: str):
        super().__init__(
            message="Failed to send error message",
            context={"booking_details": intervention_error_message},
        )


class FailedToSubmitProfile(JikingeAgentException):
    severity: ErrorSeverity = ErrorSeverity.MEDIUM

    def __init__(self, profile: dict[str, Any]):
        super().__init__(
            message="Cannot submit profile",
            context={"profile": profile},
        )
