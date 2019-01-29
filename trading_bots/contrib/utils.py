from decimal import Decimal
from typing import Optional, Union

from .money import Money


def parse_money(value: Union[str, int, Decimal, Money], currency: str) -> Optional[Decimal]:
    if value is None:
        return
    if isinstance(value, Money):
        assert value.currency == currency
        return value.amount
    return Decimal(value)
