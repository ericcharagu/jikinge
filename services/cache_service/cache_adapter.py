import json
from datetime import datetime
from typing import Any

import redis.asyncio as redis
from loguru import logger

from config import USER_SESSION_TTL, settings
from domain.schema import CacheMessage, User
from services.cache_service.cache_port import CachePort

# Set cache hold time
MESSAGE_ID_EXPIRATION_SECONDS = 300


class RedisCacheAdapter(CachePort):
    def __init__(
        self,
        port: int = settings.VALKEY_PORT,
        host: str = settings.VALKEY_HOST,
        db: int = 0,
        decode_responses: bool = True,
        client: Any = None,
    ):
        self.host: str = host
        self.port: int = port
        self.db: int = db
        self.decode_responses: bool = decode_responses
        self._client: Any = client
        self._initialised: bool = False

    async def _initialise(self) -> RedisCacheAdapter:
        """Initialize the Redis connection."""
        if not self._initialised:
            try:
                connection_pool = redis.ConnectionPool(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    decode_responses=self.decode_responses,
                )

                self._client = redis.Redis(connection_pool=connection_pool)

                # Test connection
                await self._client.ping()
                logger.info(
                    f"Successfully connected to Redis/Valkey at {self.host}:{self.port}"
                )
                self._initialised = True

            except Exception as e:
                logger.error(f"Failed to initialize Redis/Valkey connection: {e}")
                raise

        return self

    def __getattr__(self, name: str):
        """
        Proxy all Redis methods to the underlying client.
        Returns an async function that will be awaited by the caller.
        """

        async def async_method_wrapper(*args, **kwargs):
            if not self._initialised:
                await self._initialise()

            method = getattr(self._client, name)
            return await method(*args, **kwargs)

        return async_method_wrapper

    async def is_message_processed(self, message_id: str) -> bool:
        """
        Checks if the message has been processed already.
        Args:
            client: Redis client handling the session
            message_id: Unique ID attached to every message to prevent reprocessing of the same request
        Returns:
            True if message is processed
        """
        key = f"processed_wamid:{message_id}"
        was_set = await self._client.set(
            key, 1, ex=MESSAGE_ID_EXPIRATION_SECONDS, nx=True
        )
        if was_set:
            logger.info(f"New message ID acquired for processing: {message_id}")
            return True

        logger.warning(f"Duplicate message ID detected and ignored: {message_id}")
        return False

    # ==========================

    # Access Chat history

    # =============================
    async def get_chat_history(
        self, user_id: str, limit: int = 10
    ) -> list[CacheMessage]:
        """
        Retrieves the last N messages for a user from Valkey.
        Args:
            client: Redis client handling the session
            user_id: String of the user's user id number used to send the request
            limit: Max size of messages retained in the cache
        Returns:
            List of the cached messages
        """
        key = f"chat_history:{user_id}"
        try:
            # LTRIM keeps the list size fixed, preventing it from growing indefinitely
            await self._client.ltrim(key, 0, limit - 1)
            history_json = await self._client.lrange(key, 0, limit - 1)
            history: list[CacheMessage] = [
                CacheMessage(**json.loads(msg)) for msg in history_json
            ]
            history.reverse()
            logger.info(f"Retrieved {len(history)} messages for user {user_id}")
            return history
        except Exception as e:
            logger.error(f"Failed to get chat history for {user_id}: {e}")
            return []

    async def add_to_chat_history(
        self, user_id: str, cache_message: CacheMessage
    ) -> None:
        """
        Adds a new user/llm message pair to the user's chat history.
        Args:
            user_id: Phone number used to send the request
            cache_message: Custom object of the data to be stored in cache memory
        """
        key = f"chat_history:{user_id}"

        # Setting cahce payload
        message_pair: dict[str, Any] = cache_message.model_dump()

        # Uploading the
        try:
            # LPUSH adds the new message to the beginning of the list
            await self._client.lpush(key, json.dumps(message_pair))
            logger.info(f"Added new message to history for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to add to chat history for {user_id}: {e}")

    # ==========================

    # Delete Chat history

    # =============================

    async def delete_user_chat_history(self, user_id: str) -> bool:
        """
        Delete a specific user's chat history from Redis.
        Args:
            client: Redis client handling the session
            user_id:  Phone number used to send the request
        Returns:
            True: The user's history has been deleted from services.cache_service
        """
        try:
            key = f"chat_history:{user_id}"
            deleted = await self._client.delete(key)
            if deleted:
                logger.info(f"Successfully deleted chat history for user: {user_id}")
            else:
                logger.info(f"No chat history found for user: {user_id}")
            return bool(deleted)
        except Exception as e:
            logger.error(f"Failed to delete chat history for {user_id}: {e}")
            return False

    async def delete_user_cache_by_time(
        self,
        user_id: str,
        hours_ago: int = 0,
        since_timestamp: str = "",
    ) -> None:
        """
        Delete user's cache with time-based filtering
        Args:
            client: Redis client for the session
            user_id: user id number used to send the whatsapp message
            hours_ago: Delete messages older than X hours
            since_timestamp: Delete messages since specific timestamp (ISO format)
        """

        key = f"chat_history:{user_id}"
        results = {
            "deleted_count": 0,
            "remaining_count": 0,
            "user_id": user_id,
        }

        # Get all messages
        history_json = await self._client.lrange(key, 0, -1)
        if not history_json:
            logger.info(f"No chat history found for user: {user_id}")

        messages_to_keep = []
        messages_to_delete = []

        cutoff_time = None
        if hours_ago:
            cutoff_time = datetime.now(settings.NAIROBI_TZ).timestamp() - (
                hours_ago * 3600
            )
        elif since_timestamp:
            cutoff_time = datetime.fromisoformat(since_timestamp).timestamp()

        for msg_json in history_json:
            msg = json.loads(msg_json)

            if cutoff_time is None:
                # If no time filter, delete everything
                messages_to_delete.append(msg_json)
            else:
                # Check if message should be deleted based on timestamp
                msg_timestamp = msg.get("llm_response_timestamp") or msg.get(
                    "user_message_timestamp"
                )
                if msg_timestamp:
                    msg_time = datetime.fromisoformat(msg_timestamp).timestamp()
                    if msg_time <= cutoff_time:
                        messages_to_delete.append(msg_json)
                    else:
                        messages_to_keep.append(msg_json)
                else:
                    # If no timestamp, keep the message
                    messages_to_keep.append(msg_json)

        # Rebuild the list with only messages to keep
        if messages_to_keep:
            # Use transaction to replace the list atomically
            pipeline = self._client.pipeline()
            pipeline.delete(key)
            for msg in reversed(messages_to_keep):  # Reverse to maintain order
                pipeline.lpush(key, msg)
            await pipeline.execute()
        else:
            # Delete entire key if no messages to keep
            await self._client.delete(key)

        results["deleted_count"] = len(messages_to_delete)
        results["remaining_count"] = len(messages_to_keep)

        logger.info(
            f"Time-based deletion for {user_id}: deleted {len(messages_to_delete)}, kept {len(messages_to_keep)}"
        )

    async def clear_all_cache(self) -> dict[str, Any]:
        """
        Clear the entire Redis cache - delete all keys.
        This will remove ALL data from the Redis database.

        Returns:
            dict: Status of the operation with details
        """
        try:
            # Flush the entire database (clears all keys)
            await self._client.flushdb()
            logger.warning("ENTIRE REDIS CACHE CLEARED - All data deleted")
            return {
                "status": "success",
                "message": "All cache data has been cleared",
                "database": self.db,
            }
        except Exception as e:
            logger.error(f"Failed to clear entire cache: {e}")
            return {"status": "error", "message": f"Failed to clear cache: {e!s}"}

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client and self._initialised:
            await self._client.close()
            logger.info("Redis/Valkey connection closed")
            self._initialised = False

    async def save_user_session(self, user: User) -> None:
        """
        Saves the entire user session object to Redis as a JSON string.
        Args:
            redis_client: Redis session client
            user: User object
        """
        key = f"user_session:{user.user_id}"
        user_json = json.dumps(user.model_dump())
        await self._client.set(key, user_json, ex=USER_SESSION_TTL)
        logger.info(f"Saved session for user {user.user_id} to Redis.")
