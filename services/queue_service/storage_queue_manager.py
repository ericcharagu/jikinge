import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from loguru import logger

from config import settings
from domain.excepts import SystemErrorType
from domain.schema import CacheMessage, User
from services.cache_service.cache_port import CachePort
from services.database_service.store_interactions import LoggingUnitOfWork
from services.error_reporting_service import ErrorReportingService

from .consumer import ConsumerMessage, KafkaConsumer
from .producer import KafkaProducer


class StorageOperationType(str, Enum):
    """Types of storage operations"""

    CACHE_ONLY = "cache_only"
    PERSIST_ONLY = "persist_only"
    BOTH = "both"


@dataclass
class StorageOperation:
    """Represents a storage operation to be processed"""

    cache_message: dict[str, Any]  # Serialized CacheMessage
    operation_type: StorageOperationType = StorageOperationType.BOTH
    is_success: bool = True
    error_message: str | None = None
    interaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(settings.NAIROBI_TZ).isoformat()
    )
    retry_count: int = 0

    def to_json(self) -> str:
        return json.dumps(self.__dict__, default=str)


class KafkaStorageQueueManager:
    """
    Manages storage operations using Kafka as the message broker.
    Implements producer-consumer pattern with fault tolerance.
    """

    def __init__(
        self,
        cache_client: CachePort,
        session_factory,
        producer: KafkaProducer | None = None,
        consumer: KafkaConsumer | None = None,
        storage_topic: str = settings.KAFKA_STORAGE_TOPIC,
        error_topic: str = settings.KAFKA_ERROR_TOPIC,
    ):
        self.cache_client = cache_client
        self.session_factory = session_factory
        self._producer = producer or KafkaProducer()
        self._consumer = consumer or KafkaConsumer()
        self.storage_topic = storage_topic
        self.error_topic = error_topic

        # Register the consumer handler
        self._consumer.register_batch_handler(
            handler=self._process_batch, error_handler=self._handle_consumer_error
        )

        self._stats = {
            "produced": 0,
            "processed": 0,
            "success": 0,
            "failed": 0,
            "cache_updates": 0,
            "persist_updates": 0,
        }
        self._is_initialized = False

    async def initialize(self) -> None:
        """Initialize producer and consumer"""
        if self._is_initialized:
            return

        await self._producer.initialize()
        await self._consumer.start([self.storage_topic, self.error_topic])
        self._is_initialized = True
        logger.info("KafkaStorageQueueManager initialized")

    async def enqueue_storage_operation(
        self,
        cache_message: CacheMessage,
        operation_type: StorageOperationType = StorageOperationType.BOTH,
        is_success: bool = True,
        error_message: str | None = None,
        priority: bool = False,
    ) -> bool:
        """
        Enqueue a storage operation via Kafka.
        Returns True if enqueued successfully.
        """
        if not self._is_initialized:
            logger.warning("Queue manager not initialized, processing synchronously")
            return await self._process_operation_sync(
                cache_message, operation_type, is_success, error_message
            )

        try:
            # Create storage operation
            operation = StorageOperation(
                cache_message=cache_message.model_dump(),
                operation_type=operation_type,
                is_success=is_success,
                error_message=error_message,
            )

            # Produce to Kafka
            result = await self._producer.produce(
                topic=self.storage_topic,
                key=cache_message.user.user_id if cache_message.user else None,
                value=operation.to_json(),
                headers={
                    "operation_type": operation_type.value,
                    "interaction_id": operation.interaction_id,
                    "timestamp": operation.timestamp,
                },
            )

            if result:
                self._stats["produced"] += 1
                logger.debug(f"Storage operation enqueued: {operation.interaction_id}")
            else:
                logger.error(f"Failed to enqueue operation: {operation.interaction_id}")
                # Fallback to sync
                return await self._process_operation_sync(
                    cache_message, operation_type, is_success, error_message
                )

            return result

        except Exception as e:
            logger.error(f"Failed to enqueue storage operation: {e}")
            return await self._process_operation_sync(
                cache_message, operation_type, is_success, error_message
            )

    async def _process_batch(self, batch: list[ConsumerMessage]) -> None:
        """
        Process a batch of storage operations from Kafka.
        This is the consumer handler.
        """
        if not batch:
            return

        logger.info(f"Processing batch of {len(batch)} storage operations")
        tasks = []
        for msg in batch:
            if msg.topic == self.error_topic:
                # logger.warning(f"Consumer received an error-topic message: {msg.value}")
                continue

            try:
                # Parse the operation
                operation_data = msg.value
                if isinstance(operation_data, str):
                    operation_data = json.loads(operation_data)

                operation = StorageOperation(**operation_data)

                # Reconstruct CacheMessage
                cache_message = CacheMessage(**operation.cache_message)

                # Process the operation
                tasks.append(self._process_operation(operation, cache_message))
                # await self._process_operation(operation, cache_message)

                self._stats["processed"] += 1

            except Exception as e:
                logger.error(f"Failed to process message: {e}")
                # Send to error topic
                await self._send_error_to_topic(msg, str(e))
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_operation(
        self, operation: StorageOperation, cache_message: CacheMessage
    ) -> None:
        """Process a single storage operation"""
        try:
            # 1. Update cache if needed
            if operation.operation_type in [
                StorageOperationType.CACHE_ONLY,
                StorageOperationType.BOTH,
            ]:
                await self._update_cache(cache_message)
                self._stats["cache_updates"] += 1

            # 2. Persist to database if needed
            if operation.operation_type in [
                StorageOperationType.PERSIST_ONLY,
                StorageOperationType.BOTH,
            ]:
                await self._persist_to_db(cache_message)
                self._stats["persist_updates"] += 1

            # 3. Report failure if needed
            if not operation.is_success and operation.error_message:
                await self._report_failure(operation, cache_message)

            self._stats["success"] += 1

        except Exception as e:
            self._stats["failed"] += 1
            logger.error(f"Operation {operation.interaction_id} failed: {e}")

            # Retry logic
            if operation.retry_count < 3:
                operation.retry_count += 1
                logger.info(
                    f"Retrying operation {operation.interaction_id}, attempt {operation.retry_count}"
                )

                # Re-enqueue with updated retry count
                await self._producer.produce(
                    topic=self.storage_topic,
                    key=cache_message.user.user_id if cache_message.user else None,
                    value=operation.to_json(),
                    headers={
                        "retry_count": str(operation.retry_count),
                        "interaction_id": operation.interaction_id,
                    },
                )
            else:
                # Max retries exceeded
                await self._send_error_to_topic_operation(operation, str(e))

    async def _update_cache(self, cache_message: CacheMessage) -> None:
        """Update Redis cache"""
        try:
            await self.cache_client.add_to_chat_history(
                user_id=cache_message.user.user_id,
                cache_message=cache_message,
            )

            if cache_message.user:
                await self.cache_client.save_user_session(cache_message.user)

            logger.debug(f"Cache updated for {cache_message.user.user_id}")
        except Exception as e:
            logger.error(f"Cache update failed: {e}")
            raise

    async def _persist_to_db(self, cache_message: CacheMessage) -> None:
        """Persist to database"""
        async with LoggingUnitOfWork(self.session_factory) as uow:
            await uow.interaction.add(cache_message)

    async def _report_failure(
        self, operation: StorageOperation, cache_message: CacheMessage
    ) -> None:
        """Report failure to error monitoring"""
        await ErrorReportingService.report_system_error(
            Exception(operation.error_message or "Storage operation failed"),
            SystemErrorType.DATABASE_ERROR,
            cache_message.user,
            f"Failed storage operation: {operation.interaction_id}",
        )

    async def _process_operation_sync(
        self,
        cache_message: CacheMessage,
        operation_type: StorageOperationType,
        is_success: bool,
        error_message: str | None,
    ) -> bool:
        """Synchronous fallback processing"""
        try:
            # Create operation
            operation = StorageOperation(
                cache_message=cache_message.model_dump(),
                operation_type=operation_type,
                is_success=is_success,
                error_message=error_message,
            )

            # Process directly
            await self._process_operation(operation, cache_message)
            return True

        except Exception as e:
            logger.error(f"Sync processing failed: {e}")
            return False

    async def _send_error_to_topic(self, msg: ConsumerMessage, error: str) -> None:
        """Send failed message to error topic"""
        await self._producer.produce(
            topic=self.error_topic,
            key=msg.key,
            value={
                "original_message": msg.value,
                "error": error,
                "timestamp": datetime.now(settings.NAIROBI_TZ).isoformat(),
                "topic": msg.topic,
                "partition": msg.partition,
                "offset": msg.offset,
            },
        )

    async def _send_error_to_topic_operation(
        self, operation: StorageOperation, error: str
    ) -> None:
        """Send failed operation to error topic"""
        await self._producer.produce(
            topic=self.error_topic,
            key=operation.interaction_id,
            value={
                "operation": operation.to_json(),
                "error": error,
                "timestamp": datetime.now(settings.NAIROBI_TZ).isoformat(),
            },
        )

    async def _handle_consumer_error(self, error: Exception) -> None:
        """Handle consumer errors"""
        logger.error(f"Consumer error: {error}")
        await ErrorReportingService.report_system_error(
            error,
            SystemErrorType.RUNTIME_EXCEPTION,
            User(user_id="system"),
            "Kafka consumer error",
        )

    async def stop(self) -> None:
        """Stop the queue manager"""
        self._is_initialized = False
        await self._consumer.stop()
        await self._producer.close()
        logger.info(f"KafkaStorageQueueManager stopped. Stats: {self._stats}")

    def get_stats(self) -> dict:
        """Get processing statistics"""
        return {**self._stats, "is_initialized": self._is_initialized}

    @asynccontextmanager
    async def lifecycle(self):
        """Context manager for queue lifecycle"""
        await self.initialize()
        try:
            yield self
        finally:
            await self.stop()
