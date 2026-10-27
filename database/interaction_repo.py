from models import CacheMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import AsyncSessionLocal
from .orm_schema import InteractionLogOrm


class InteractionLogRepo:
    """Service layer for interaction log operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, interaction: CacheMessage) -> None:
        """Add a new interaction log."""
        # SQLAlchemy handles dict serialization automatically with JSONB
        interaction_orm = InteractionLogOrm(
            user_id=interaction.user.user_id,
            cart_id=interaction.cart_id,
            user_message=interaction.user_message,
            llm_response=interaction.llm_response,
            llm_message_type=interaction.llm_message_type,
            intent=interaction.intent,
            metrics=interaction.timings,
            cart_snapshot=interaction.user.cart.model_dump(),
        )
        self.session.add(interaction_orm)
        # Flush to assign ID but don't commit yet
        await self.session.flush()

    async def get_by_cart_id(self, cart_id: str) -> list[InteractionLogOrm]:
        """Get all interactions for a cart."""
        result = await self.session.execute(
            select(InteractionLogOrm).where(InteractionLogOrm.cart_id == cart_id)
        )
        return result.scalars().all()

    async def get_by_llm_message_type(
        self, llm_message_type: str
    ) -> list[InteractionLogOrm]:
        """Get all instances that returned a certain type of LLM message."""
        result = await self.session.execute(
            select(InteractionLogOrm).where(
                InteractionLogOrm.llm_message_type == llm_message_type
            )
        )
        return result.scalars().all()

    async def get_by_user_id(self, user_id: str) -> list[InteractionLogOrm]:
        """Get all interactions for a user_id number."""
        result = await self.session.execute(
            select(InteractionLogOrm).where(InteractionLogOrm.user_id == user_id)
        )
        return result.scalars().all()


class InteractionLogService:
    """
    Persistence Layer: Responsible for Database I/O using ORM.
    """

    @staticmethod
    async def add_interaction_to_db(
        payload: CacheMessage, session: AsyncSession | None = None
    ) -> None:
        """
        Persist an interaction log using ORM.

        Args:
            payload: The cache message to persist
            session: Optional session (if using UoW, pass the session from there)
        """
        if session:
            # Use provided session (from UoW)
            service = InteractionLogRepo(session)
            await service.add(payload)
        else:
            # Create a new session if none provided (legacy support)
            async with AsyncSessionLocal() as new_session, new_session.begin():
                service = InteractionLogRepo(new_session)
                await service.add(payload)
                # No need for explicit commit due to begin() context manager

    @staticmethod
    async def get_interactions_by_cart(
        cart_id: str, session: AsyncSession
    ) -> list[InteractionLogOrm]:
        """Get interactions using ORM with explicit session."""
        service = InteractionLogRepo(session)
        return await service.get_by_cart_id(cart_id)
