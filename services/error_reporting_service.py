import traceback
from datetime import datetime

from dependencies import retry_decorator
from loguru import logger
from models import InterventionError, User

from config import settings
from domain.excepts import InterventionMessageDeliveryException

from .api import api_base


class ErrorReportingService:
    def __init__(
        self, intervention_error: InterventionError, user_details: User
    ) -> None:
        self.intervention_error = intervention_error
        self.user_details = user_details

    def _create_error_messages(self) -> tuple[str, str]:
        # Generate the error message
        email_error_message: str = self._generate_email_intervention_message()
        sms_error_message: str = self._generate_sms_intervention_message()

        return email_error_message, sms_error_message

    @retry_decorator
    async def send_message(self) -> None:
        """
        Generate and send error message to human agent

        Args:
            user_details: Current user session information
        """
        email_error_message, sms_error_message = self._create_error_messages()

        payload: dict[str, str] = {
            "email_content": email_error_message,
            "sms_content": sms_error_message,
        }

        # Send the error message via Lane notify api
        response = await api_base.post_api_request(settings.INTERVENTION_API, payload)

        if response.status_code not in [200, 201]:
            logger.error("Failed to send error message to human intervention number")

            raise InterventionMessageDeliveryException(self.sms_error_message)
        else:
            logger.info("The human agent has been notified.")

    def _generate_sms_intervention_message(self) -> str:
        """Generate SMS message for human agent intervention"""
        return f"Hi. I have encountered an issue that requires your assistance. The user {self.user_details.user_id} was flagged for {self.intervention_error.flag_reason}"

    def _generate_email_intervention_message(self) -> str:
        """
        Generate error message sent to human agent for intervention
        Args:
            user_details: current user
        Returns:
            String of the generated error template
        """

        template = """
            Hi,I have encountered a problematic order that requires manual intervention.

            **Order Details:**
            - **Customer Phone**: {user_id}
            - **Order Location**: {address}
            - **Cart Total**: KES {cart_total}
            - **Items**: {item_list}
            - **Cart Created**: {created_at}
            - **Cart Last Updated**: {updated_at}

            **Issue Information:**
            - **Flag Reason**: {flag_reason}
            - **Error Type**: {error_type}
            - **Detection Time**: {detection_time}
            - **Additional Context**: {additional_notes}

            This order was flagged at {detection_time} and requires manual review. The cart is set to expire at {expires_at}.

            Please review this order and take appropriate action.

        """

        return template.format(
            user_id=self.user_details.user_id,
            address=self.user_details.address,
            created_at=self.user_details.created_at,
            updated_at=self.user_details.updated_at,
            flag_reason=self.intervention_error.flag_reason,
            error_type=self.intervention_error.error_type,
            detection_time=self.intervention_error.detection_time,
            additional_notes=self.intervention_error.additional_notes,
            expires_at=self.user_details.expires_at,
        )

    # Intervention Error helper message
    @staticmethod
    async def report_system_error(
        error: Exception, error_type: str, user: User, context: str = ""
    ):
        """Helper to log and send intervention alerts."""
        logger.error(
            f"System Error [{error_type}]: {error!s} and {traceback.print_exc()}"
        )

        intervention_error = InterventionError(
            flag_reason=f"Agent Flow Failure: {error!s}",
            error_type=error_type,
            detection_time=datetime.now(settings.NAIROBI_TZ),
            additional_notes=f"Context: {context}\n\nTraceback: {error!s}",
        )

        # Use the intervention handler to send the message
        error_service = ErrorReportingService(intervention_error, user)
        await error_service.send_message()
