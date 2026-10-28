import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from confluent_kafka import Consumer, TopicPartition
from loguru import logger

from config import settings


@dataclass
class ConsumerMessage:
    """Wrapper for Kafka messages"""

    topic: str
    partition: int
    offset: int
    key: str | None
    value: Any
    headers: dict[str, str]
    timestamp: datetime


class KafkaConsumer:
    """
    Asynchronous Kafka consumer with batch processing and error handling.
    """

    def __init__(
        self,
        bootstrap_servers: str = settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id: str = settings.KAFKA_GROUP_ID,
        consumer_count: int = settings.KAFKA_CONSUMER_COUNT,
        auto_offset_reset: str = settings.KAFKA_AUTO_OFFSET_RESET,
        enable_auto_commit: bool = settings.KAFKA_ENABLE_AUTO_COMMIT,
        auto_commit_interval_ms: int = settings.KAFKA_AUTO_COMMIT_INTERVAL_MS,
        session_timeout_ms: int = settings.KAFKA_SESSION_TIMEOUT_MS,
        max_poll_interval_ms: int = settings.KAFKA_MAX_POLL_INTERVAL_MS,
        batch_size: int = settings.KAFKA_MAX_POLL_RECORDS,
        heartbeat_interval_ms: int = 3000,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.consumer_count = consumer_count
        self.auto_offset_reset = auto_offset_reset
        self.enable_auto_commit = enable_auto_commit
        self.auto_commit_interval_ms = auto_commit_interval_ms
        self.session_timeout_ms = session_timeout_ms
        self.max_poll_interval_ms = max_poll_interval_ms
        self.batch_size = batch_size

        self._consumers: list[Consumer] = []
        self._is_running = False
        self._consumer_tasks: list[asyncio.Task] = []
        self._message_handler: Callable[[ConsumerMessage], Awaitable[None]] | None = (
            None
        )
        self._batch_handler: (
            Callable[[list[ConsumerMessage]], Awaitable[None]] | None
        ) = None
        self._error_handler: Callable[[Exception], Awaitable[None]] | None = None

    def register_message_handler(
        self,
        handler: Callable[[ConsumerMessage], Awaitable[None]],
        error_handler: Callable[[Exception], Awaitable[None]] | None = None,
    ) -> None:
        """Register a handler for individual messages"""
        self._message_handler = handler
        self._error_handler = error_handler

    def register_batch_handler(
        self,
        handler: Callable[[list[ConsumerMessage]], Awaitable[None]],
        error_handler: Callable[[Exception], Awaitable[None]] | None = None,
    ) -> None:
        """Register a handler for batch processing"""
        self._batch_handler = handler
        self._error_handler = error_handler

    def _create_consumer(self, consumer_id: int) -> Consumer:
        """Create a Kafka consumer instance"""
        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": f"{self.group_id}-{consumer_id}",
            "auto.offset.reset": self.auto_offset_reset,
            "enable.auto.commit": self.enable_auto_commit,
            "auto.commit.interval.ms": self.auto_commit_interval_ms,
            "session.timeout.ms": self.session_timeout_ms,
            "max.poll.interval.ms": self.max_poll_interval_ms,  # CORRECT PROPERTY
            "heartbeat.interval.ms": 3000,
            "enable.partition.eof": False,
            "partition.assignment.strategy": "roundrobin",
        }

        # Remove any None values
        config = {k: v for k, v in config.items() if v is not None}

        return Consumer(config)

    async def start(self, topics: list[str]) -> None:
        """
        Start consuming messages from the specified topics.
        """
        if self._is_running:
            logger.warning("Consumer already running")
            return

        if not self._message_handler and not self._batch_handler:
            raise ValueError(
                "No handler registered. Call register_message_handler() or register_batch_handler()"
            )

        self._is_running = True

        # Create consumers with different group IDs for parallelism
        for i in range(self.consumer_count):
            try:
                consumer = self._create_consumer(i)
                consumer.subscribe(topics)
                self._consumers.append(consumer)

                # Start consumer task
                task = asyncio.create_task(self._consumer_loop(consumer, i))
                self._consumer_tasks.append(task)
                logger.info(f"Consumer {i} created and subscribed to {topics}")
            except Exception as e:
                logger.error(f"Failed to create consumer {i}: {e}")
                raise

        logger.info(
            f"Started {self.consumer_count} Kafka consumers for topics: {topics}"
        )

    async def _consumer_loop(self, consumer: Consumer, consumer_id: int) -> None:
        """Main consumer loop with proper pause/resume for long processing"""
        logger.info(f"Consumer {consumer_id} started")

        while self._is_running:
            try:
                # Poll for messages - this is a blocking call
                msg = await asyncio.to_thread(consumer.poll, timeout=1.0)

                if msg is None:
                    await asyncio.sleep(0.01)
                    continue

                if msg.error():
                    logger.error(f"Consumer {consumer_id} error: {msg.error()}")
                    continue

                # Parse the message
                parsed_msg = self._parse_message(msg)

                # Process based on registered handler
                if self._message_handler:
                    # Individual message processing with pause/resume
                    await self._process_message_with_pause(consumer, parsed_msg)
                elif self._batch_handler:
                    # Batch processing - collect more messages
                    await self._process_batch(consumer, consumer_id)

            except asyncio.CancelledError:
                logger.info(f"Consumer {consumer_id} cancelled")
                break
            except Exception as e:
                logger.error(f"Consumer {consumer_id} loop error: {e}")
                if self._error_handler:
                    await self._error_handler(e)
                await asyncio.sleep(1)

    async def _process_message_with_pause(
        self, consumer: Consumer, message: ConsumerMessage
    ) -> None:
        """Process a single message with pause/resume to prevent max.poll.interval issues"""
        try:
            # Create TopicPartition for the message's partition
            partition = TopicPartition(message.topic, message.partition)

            # Pause this partition to stop receiving more messages
            consumer.pause([partition])

            # Process the message
            await self._message_handler(message)

            # Resume the partition after processing
            consumer.resume([partition])

            # Commit offset if auto-commit is disabled
            if not self.enable_auto_commit:
                await asyncio.to_thread(consumer.commit, message)

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            if self._error_handler:
                await self._error_handler(e)
            # Ensure we resume even on error
            try:
                consumer.resume([TopicPartition(message.topic, message.partition)])
            except Exception:
                logger.error("Cannot create topic partition...")
            raise

    async def _process_batch(self, consumer: Consumer, consumer_id: int) -> None:
        """Collect and process a batch of messages with pause/resume"""
        batch = []
        partitions_seen = set()

        # Collect up to batch_size messages with a timeout
        poll_timeout = 0.05  # 50ms per poll
        max_polls = self.batch_size * 2  # Safety limit

        for _ in range(max_polls):
            msg = await asyncio.to_thread(consumer.poll, timeout=poll_timeout)

            if msg is None:
                # No more messages available
                break

            if msg.error():
                if msg.error().code() != 0:  # Not a normal error
                    logger.error(f"Batch poll error: {msg.error()}")
                break

            parsed = self._parse_message(msg)
            batch.append(parsed)
            partitions_seen.add((parsed.topic, parsed.partition))

            # Stop if we've collected enough
            if len(batch) >= self.batch_size:
                break

        if not batch:
            return

        # Process batch with pause/resume
        partitions = [
            TopicPartition(topic, partition) for topic, partition in partitions_seen
        ]

        try:
            # Pause to prevent more messages while processing
            consumer.pause(partitions)

            # Create a task to process the batch
            processing_task = asyncio.create_task(self._batch_handler(batch))

            # While the task is running, continue to poll to keep the heartbeat alive
            while not processing_task.done():
                await asyncio.to_thread(consumer.poll, timeout=poll_timeout)
                await asyncio.sleep(1)  # Check every second

            await processing_task  # Ensure exceptions are raised
            # Resume after processing
            consumer.resume(partitions)

            # Commit offsets if auto-commit is disabled
            if not self.enable_auto_commit:
                await asyncio.to_thread(consumer.commit)

        except Exception as e:
            logger.error(f"Batch processing error: {e}")
            if self._error_handler:
                await self._error_handler(e)
            # Ensure we resume even on error
            try:
                consumer.resume(partitions)
            except Exception:
                logger.error("Faile to resume after batch processing error")
            raise

    async def stop(self) -> None:
        """Stop all consumers gracefully"""
        logger.info("Stopping Kafka consumers...")
        self._is_running = False

        # Cancel consumer tasks
        for task in self._consumer_tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete with timeout
        if self._consumer_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._consumer_tasks, return_exceptions=True),
                    timeout=10.0,
                )
            except asyncio.TimeoutError:
                logger.warning("Consumer tasks timed out during shutdown")

        # Close consumers
        for consumer in self._consumers:
            try:
                await asyncio.to_thread(consumer.close)
                logger.debug("Consumer closed successfully")
            except Exception as e:
                logger.error(f"Error closing consumer: {e}")

        self._consumers.clear()
        self._consumer_tasks.clear()
        logger.info("All Kafka consumers stopped")

    def _parse_message(self, msg) -> ConsumerMessage:
        """Parse a Kafka message into a ConsumerMessage object"""
        try:
            value = json.loads(msg.value().decode("utf-8"))
        except json.JSONDecodeError, AttributeError, UnicodeDecodeError:
            value = msg.value().decode("utf-8") if msg.value() else None

        headers = {}
        if msg.headers():
            for key, val in msg.headers():
                headers[key] = val.decode("utf-8") if val else None

        return ConsumerMessage(
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
            key=msg.key().decode("utf-8") if msg.key() else None,
            value=value,
            headers=headers,
            timestamp=datetime.fromtimestamp(msg.timestamp()[1] / 1000),
        )

    async def commit_offsets(self) -> None:
        """Manually commit offsets if auto-commit is disabled"""
        if not self.enable_auto_commit:
            for consumer in self._consumers:
                await asyncio.to_thread(consumer.commit)

    @asynccontextmanager
    async def lifecycle(self, topics: list[str]):
        """Context manager for consumer lifecycle"""
        await self.start(topics)
        try:
            yield self
        finally:
            await self.stop()
