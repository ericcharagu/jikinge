from decimal import Decimal

from services.database_service.deductibles_repo import deductibles_repo

from domain.schema import Deductible
from services.database_service.orm_schema import DeductiblesOrm


async def _all_deductibles() -> list[dict[str, bool | Deductible]]:
    deductibles: list[DeductiblesOrm] = await deductibles_repo.get_all_deductibles()
    return [
        {"selected": "false", "deductible": deductible(deductible["deductible_name"])}
        for deductible in enumerate(deductibles)
    ]


def total_deductible_discount(deductible: list[Deductible]) -> Decimal:
    deductible_discount: list[DeductiblesOrm] = (
        deductibles_repo.get_deductible_discount()
    )
    return sum(
        Decimal(deductible.deductible_value) for deductible in deductible_discount
    )


def total_deductible_levies(deductible: list[Deductible]) -> Decimal:
    deductible_levies: list[DeductiblesOrm] = deductibles_repo.get_deductible_levies()
    return sum(Decimal(deductible.deductible_value) for deductible in deductible_levies)


def calculate_total_payable(
    base_rate: Decimal, discount_head: list[Deductible]
) -> Decimal:
    for deductible in discount_head:
        if "%" in deductible.deductible_value:
            base_rate = base_rate * (1 - deductible.deductible_value)
        base_rate - deductible.deductible_value
    return base_rate
