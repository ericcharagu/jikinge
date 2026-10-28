import json
from datetime import datetime

from config import settings
from domain.excepts import UserCreationException
from domain.schema import CacheMessage, User
from services.cache_service.cache_port import CachePort


class UserService:
    def __init__(self, cache: CachePort):
        self.cache = cache
        self.ttl = 3600  # 1 hour

    async def get_or_create_user(self, user_id: str) -> User:
        try:
            user_json = await self.cache.get(f"user_session:{user_id}")

            if user_json:
                data = json.loads(user_json)

                # Convert car make from list to str
                if isinstance(data["car_make"], list):
                    data["car_make"] = "".join(data["car_make"])

                user = User(**data)
                user.updated_at = datetime.now(settings.NAIROBI_TZ).isoformat()
                await self.cache.save_user_session(user)
                return user

            # Create New User
            new_user = User(
                user_id=user_id,
                created_at=datetime.now(settings.NAIROBI_TZ).isoformat(),
                referring_agent=settings.DEFAULT_REFERRAL_CODE,
            )

            await self.cache.save_user_session(new_user)
            return new_user
        except Exception as e:
            raise UserCreationException(user_id, e) from e

    async def get_chat_history(self, user_id: str) -> list[CacheMessage]:
        return await self.cache.get_chat_history(user_id)
