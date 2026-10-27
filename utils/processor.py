import os
from typing import Any

from excepts import (
    JikingeAgentException,
)
from fastapi import HTTPException, Request
from llm.llm_schema import PlannerAgentInput, PlannerAgentOutput
from loguru import logger
from messaging.messages_schema import TextMessage

from cache.cache_port import CachePort
from domain.excepts import SystemErrorType
from domain.schema import (
    CacheMessage,
    User,
)
from llm.agents import planner_agent

from .error_reporting_service import ErrorReportingService
from .media_service import MediaService
from .sender_service import (
    PLATFORM,
    MessageSender,
    SenderService,
    sender,
)
from .services.user_service import UserService
from .whatsapp.whatsapp_schema import MessageRequest
from .whatsapp.whatsapp_service import (
    WhatsAppMessengerService,
    whatsapp_messenger_service,
)


class MessageOrchestrator:
    def __init__(
        self,
        cache_client: CachePort,
        queue_manager,
        platform: PLATFORM,
        sender: SenderService = sender,
    ):
        self.cache_client: CachePort = cache_client
        self.user_service: UserService = UserService(self.cache_client)
        self.media_service: MediaService = MediaService()
        self.queue_manager: Any = queue_manager
        self.notification_service: WhatsAppMessengerService = whatsapp_messenger_service
        self._sender: SenderService = sender
        self._platform: PLATFORM = platform

    @property
    def sender(self) -> MessageSender:
        return self._sender.get(platform=self._platform)

    def _construct_planner_agent_output(
        self, agent_output_dict: dict[str, Any]
    ) -> PlannerAgentOutput:
        planner_agent_output: PlannerAgentOutput = agent_output_dict.get("result")

        # Create any additional text messages
        if planner_agent_output.response_text:
            additional_customer_instructions = TextMessage(
                body=planner_agent_output.response_text
            )
            planner_agent_output.messages.append(additional_customer_instructions)
        return planner_agent_output

    async def _log_interaction(
        self,
        user: User,
        message_request: MessageRequest,
        planner_agent_output: PlannerAgentOutput,
    ) -> None:
        # Create the cache object for storing
        cache_message: CacheMessage = CacheMessage(
            user=user,
            user_message=message_request.user_message or message_request.image_caption,
            llm_response=planner_agent_output.response_text,
            llm_message_type=planner_agent_output.llm_message_type,
            intent=planner_agent_output.intent_metadata.get("intent", "unknown"),
            cart_id=user.cart.cart_id if user.cart else "",
            timings=planner_agent_output.timings,
        )
        # Save to the Redis cache first for quick recovery
        await self.cache_client.add_to_chat_history(
            user_id=user.user_id, cache_message=cache_message
        )
        await self.cache_client.save_user_session(user)
        await self.queue_manager.enqueue_storage_operation(cache_message)

    async def _handle_exception(self, error: JikingeAgentException, user: User):
        """
        Handle any expected errors from the application

        Args:
            error (JikingeAgentException): Custom exceptions
            user (User): user's message that produces the error
        """

        # 1. Update Metrics
        # metrics.increment_error_count(error.__class__.__name__)

        # 2. Notify User
        text_message = TextMessage(body=error.user_friendly_message)
        await self.notification_service.send_whatsapp_text(
            message=text_message,
            user_id=user.user_id,
        )

        await ErrorReportingService.report_system_error(
            error=error,
            error_type=SystemErrorType.RUNTIME_EXCEPTION,
            user=user,
        )

    async def handle_request(self, request: Request, message_request: MessageRequest):
        """
        Main request processing function

        Args:
            request (Request): FastApi internal configuration sent with every request
            message_request (MessageRequest): Default agent input object
        """

        media_path: str = ""

        try:
            user: User = await self.user_service.get_or_create_user(
                user_id=message_request.user_id
            )

            if message_request.media_id:
                media_path: str = await self.media_service.download_whatsapp_media(
                    message_request.media_id
                )

            # Setting user address if present and is within Nairobi
            if message_request.latitude and message_request.longitude:
                user.address = f"{message_request.latitude},{message_request.longitude}"

            # Get chat history
            history: list[CacheMessage] = await self.user_service.get_chat_history(
                message_request.user_id
            )

            # Build the input object for the AI
            agent_input: PlannerAgentInput = PlannerAgentInput(
                user_message=message_request.user_message
                or message_request.image_caption,
                chat_history=history,
                user=user,
                request=request,
            )
            # Agent responses
            agent_output_dict = await planner_agent.agent_flow(
                planner_agent_input=agent_input
            )
            # Extract the object from the results
            planner_agent_output: PlannerAgentOutput = (
                self._construct_planner_agent_output(agent_output_dict)
            )

            # Send the response
            await self.sender.send_all(
                user_id=user.user_id,
                messages=planner_agent_output.messages,
            )

            # Update the user
            user = planner_agent_output.updated_user_object or user

            # Log the interaction
            await self._log_interaction(user, message_request, planner_agent_output)
            return planner_agent_output.messages

        except (JikingeAgentException, Exception) as e:
            # await self._handle_known_error(e, user)
            logger.info(f"Error {e}. Reintroduce notification system when done")
            raise HTTPException(status_code=500, detail=f"Agent error: {e!s}")

        finally:
            # Clean up media files
            if media_path and os.path.exists(media_path):
                try:
                    os.remove(media_path)
                except Exception as e:
                    logger.warning(f"Failed to clean up media file {media_path}: {e}")
