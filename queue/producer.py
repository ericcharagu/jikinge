import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from confluent_kafka import KafkaError, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from loguru import logger

from config import settings


class KafkaProducer:
    """
    Asynchronous Kafka producer wrapper with retry and error handling.
    """

    def __init__(
        self,
        bootstrap_servers: str = settings.KAFKA_BOOTSTRAP_SERVERS,
        client_id: str = "lane-producer",
        acks: str = settings.KAFKA_ACKS,
        retries: int = settings.KAFKA_RETRIES,
        linger_ms: int = settings.KAFKA_LINGER_MS,
        batch_size_kb: int = settings.KAFKA_BATCH_SIZE_KB,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self.acks = acks
        self.retries = retries
        self.linger_ms = linger_ms
        self.batch_size_kb = batch_size_kb

        self._producer: Producer | None = None
        self._loop = asyncio.get_event_loop()
        self._is_initialized = False

    def _create_producer(self) -> Producer:
        """Create and configure the Kafka producer"""
        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "client.id": self.client_id,
            "acks": self.acks,
            "retries": self.retries,
            "linger.ms": self.linger_ms,
            "batch.size": self.batch_size_kb * 1024,  # Convert KB to bytes
            "compression.type": "snappy",
            "max.in.flight.requests.per.connection": 5,
            "enable.idempotence": True,
            "message.send.max.retries": self.retries,
            "retry.backoff.ms": 100,
        }
        return Producer(config)

    async def initialize(self) -> None:
        """Initialize the producer and ensure topics exist"""
        try:
            self._producer = self._create_producer()
            self._is_initialized = True

            # Ensure required topics exist
            await self._ensure_topics()

            # Start the background flush loop
            asyncio.create_task(self._flush_loop())

            logger.info(f"Kafka producer initialized for {self.bootstrap_servers}")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            raise

    async def _ensure_topics(self) -> None:
        """Create required topics if they don't exist"""
        admin = AdminClient({"bootstrap.servers": self.bootstrap_servers})

        new_topics = [
            NewTopic(
                settings.KAFKA_STORAGE_TOPIC, num_partitions=3, replication_factor=1
            ),
            NewTopic(
                settings.KAFKA_ERROR_TOPIC, num_partitions=1, replication_factor=1
            ),
            NewTopic(
                settings.KAFKA_HEALTH_TOPIC, num_partitions=1, replication_factor=1
            ),
        ]

        try:
            # list_topics is blocking
            metadata = await asyncio.to_thread(admin.list_topics, timeout=10)
            existing_names = set(metadata.topics.keys())
            to_create = [t for t in new_topics if t.topic not in existing_names]

            if to_create:
                fs = admin.create_topics(to_create)
                for topic_name, future in fs.items():
                    await asyncio.to_thread(future.result)
                    logger.info(f"Topic {topic_name} created")
        except Exception as e:
            logger.error(f"Failed to ensure topics: {e}")

    async def _flush_loop(self) -> None:
        while self._is_initialized:
            if self._producer:
                await asyncio.to_thread(self._producer.flush, 0.1)
            await asyncio.sleep(0.5)

    async def produce(
        self,
        topic: str,
        key: str | None,
        value: Any,
        headers: dict[str, str] | None = None,
        timeout: int = settings.KAFKA_PRODUCER_TIMEOUT,
    ) -> bool:
        """
        Produce a message to Kafka asynchronously.
        Returns True if successful, False otherwise.
        """
        if not self._is_initialized or not self._producer:
            logger.error("Producer not initialized")
            return False

        try:
            # Serialize value to JSON if not already a string
            if not isinstance(value, str):
                value = json.dumps(value, default=self._json_serializer)

            # Prepare headers
            kafka_headers = []
            if headers:
                for k, v in headers.items():
                    kafka_headers.append((k, v.encode("utf-8")))

            # Use a future to get delivery report
            future = asyncio.Future()

            def delivery_report(err, msg):
                if err:
                    future.set_exception(KafkaError(str(err)))
                else:
                    future.set_result(True)

            # Produce message
            self._producer.produce(
                topic=topic,
                key=key.encode("utf-8") if key else None,
                value=value.encode("utf-8"),
                headers=kafka_headers,
                callback=delivery_report,
            )

            # Wait for delivery
            try:
                result = await asyncio.wait_for(future, timeout=timeout)
                logger.debug(f"Message produced to {topic} with key {key}")
                return result
            except asyncio.TimeoutError:
                logger.error(f"Kafka produce timeout after {timeout}s")
                return False

        except Exception as e:
            logger.error(f"Failed to produce message: {e}")
            return False

    async def produce_batch(
        self,
        topic: str,
        messages: list[tuple[str | None, Any, dict[str, str] | None]],
    ) -> list[bool]:
        """
        Produce multiple messages in batch.
        Each message is (key, value, headers)
        """
        results = []
        for key, value, headers in messages:
            result = await self.produce(topic, key, value, headers)
            results.append(result)
        return results

    @staticmethod
    def _json_serializer(obj):
        """Custom JSON serializer for datetime objects"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode()
        raise TypeError(f"Type {type(obj)} not serializable")

    async def close(self) -> None:
        """Close the producer"""
        self._is_initialized = False
        if self._producer:
            self._producer.flush()
            logger.info("Kafka producer closed")

    @asynccontextmanager
    async def lifecycle(self):
        """Context manager for producer lifecycle"""
        await self.initialize()
        try:
            yield self
        finally:
            await self.close()
