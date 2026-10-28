from orm_schema import DeductiblesOrm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.schema import DeductibleType

from .base import AsyncSessionLocal


class DeductiblesRepo:
    """Service layer for interaction log operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_detuctables_by_type(
        self, deductible_type: str
    ) -> list[DeductiblesOrm]:
        """Get all interactions for a cart."""
        result = await self.session.execute(
            select(DeductiblesOrm).where(
                DeductiblesOrm.deductible_type == deductible_type
            )
        )
        return result.scalars().all()

    async def get_deductible_levies(self) -> list[DeductiblesOrm]:
        return await self._get_detuctables_by_type(DeductibleType.LEVIES.value)

    async def get_deductible_discounts(self) -> list[DeductiblesOrm]:
        return await self._get_detuctables_by_type(DeductibleType.DISCOUNT.value)


async def _initiate_deductibles_repo() -> DeductiblesRepo:
    async with AsyncSessionLocal() as session:
        yield DeductiblesRepo(session)


deductibles_repo: DeductiblesRepo = _initiate_deductibles_repo()
