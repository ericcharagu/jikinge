from decimal import Decimal

from database.deductables_repo import deductables_repo
from database.orm_schema import DeductablesOrm
from domain.schema import Deductable


async def _all_deductables() -> list[dict[str, bool | Deductable]]:
    deductables: list[DeductablesOrm] = await deductables_repo.get_all_deductables()
    return [
        {"selected": "false", "deductable": Deductable(deductable["deductable_name"])}
        for deductable in enumerate(deductables)
    ]


def total_deductable_discount(deductable: list[Deductable]) -> Decimal:
    deductable_discount: list[DeductablesOrm] = (
        deductables_repo.get_deductable_discount()
    )
    return sum(
        Decimal(deductable.deductable_value) for deductable in deductable_discount
    )


def total_deductable_levies(deductable: list[Deductable]) -> Decimal:
    deductable_levies: list[DeductablesOrm] = deductables_repo.get_deductable_levies()
    return sum(Decimal(deductable.deductable_value) for deductable in deductable_levies)


def calculate_total_payable(
    base_rate: Decimal, discount_head: list[Deductable]
) -> Decimal:
    for deductable in discount_head:
        if "%" in deductable.deductable_value:
            base_rate = base_rate * (1 - deductable.deductable_value)
        base_rate - deductable.deductable_value
    return base_rate
