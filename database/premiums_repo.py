from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .orm_schema import PremiumsOrm


class PremiumsRepo:
    """Interaction with the premiums database."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_premiums(self) -> list[PremiumsOrm]:
        """Get all premiums"""
        result = await self.session.execute(select(PremiumsOrm))
        return result.scalars().all()
