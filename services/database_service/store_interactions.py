from sqlalchemy.ext.asyncio import AsyncSession

from .base import AsyncSessionLocal
from .interaction_repo import InteractionLogRepo


class LoggingUnitOfWork:
    """
    Unit of Work pattern for managing database transactions.
    """

    def __init__(self, session_factory=AsyncSessionLocal) -> None:
        self.session_factory = session_factory
        self.session: AsyncSession | None = None
        self.interaction: InteractionLogRepo | None = None

    async def __aenter__(self):
        self.session = self.session_factory()
        self.interaction = InteractionLogRepo(self.session)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.session.rollback()
        else:
            await self.session.commit()
        await self.session.close()
        self.session = None
        self.interaction = None

    async def commit(self):
        """Explicit commit if needed."""
        await self.session.commit()

    async def rollback(self):
        """Explicit rollback if needed."""
        await self.session.rollback()
