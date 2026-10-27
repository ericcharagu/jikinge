from orm_schema import DeductablesOrm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.schema import DeductableType

from .base import AsyncSessionLocal


class DeductablesRepo:
    """Service layer for interaction log operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_detuctables_by_type(
        self, deductable_type: str
    ) -> list[DeductablesOrm]:
        """Get all interactions for a cart."""
        result = await self.session.execute(
            select(DeductablesOrm).where(
                DeductablesOrm.deductable_type == deductable_type
            )
        )
        return result.scalars().all()

    async def get_deductable_levies(self) -> list[DeductablesOrm]:
        return await self._get_detuctables_by_type(DeductableType.LEVIES.value)

    async def get_deductable_discounts(self) -> list[DeductablesOrm]:
        return await self._get_detuctables_by_type(DeductableType.DISCOUNT.value)


async def _initiate_deductables_repo() -> DeductablesRepo:
    async with AsyncSessionLocal() as session:
        yield DeductablesRepo(session)


deductables_repo = _initiate_deductables_repo()
