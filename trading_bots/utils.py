import math
from datetime import datetime
from decimal import Decimal
from typing import Any, Tuple, Union

import maya

from trading_bots.contrib.money import Money

DECIMALS = {
    # Fiat
    'ARS': 2,
    'BRL': 2,
    'CLP': 2,
    'COP': 2,
    'EUR': 2,
    'PEN': 2,
    'USD': 2,
    # Crypto
    'BCH': 8,
    'BTC': 8,
    'ETH': 8,
    'LTC': 8,
}


def get_iso_time_str(timestamp: Union[int, float, str, datetime]=None) -> str:
    """Get the ISO time string from a timestamp or date obj. Returns current time str if no timestamp is passed"""
    if isinstance(timestamp, (int, float)):
        maya_dt = maya.MayaDT(timestamp)
    elif isinstance(timestamp, str):
        maya_dt = maya.when(timestamp)
    elif timestamp is None:
        maya_dt = maya.now()
    else:
        raise ValueError(f'`{type(timestamp)}` is not supported')
    return maya_dt.iso8601()


def truncate(value: Decimal, n_digits: int) -> Decimal:
    """Truncates a value to a number of decimals places"""
    return Decimal(math.trunc(value * (10 ** n_digits))) / (10 ** n_digits)


def truncate_to(value: Decimal, currency: str) -> Decimal:
    """Truncates a value to the number of decimals corresponding to the currency"""
    decimal_places = DECIMALS.get(currency.upper(), 2)
    return truncate(value, decimal_places)


def truncate_money(money: Money) -> Money:
    """Truncates money amount to the number of decimals corresponding to the currency"""
    amount = truncate_to(money.amount, money.currency)
    return Money(amount, money.currency)


def spread_value(value: Decimal, spread_p: Decimal) -> Tuple[Decimal, Decimal]:
    """Returns a lower and upper value separated by a spread percentage"""
    upper = value * (1 + spread_p)
    lower = value / (1 + spread_p)
    return lower, upper


def spread_money(money: Money, spread_p: Decimal) -> Tuple[Money, Money]:
    """Returns a lower and upper money amount separated by a spread percentage"""
    upper, lower = spread_value(money.amount, spread_p)
    return Money(upper, money.currency), Money(lower, money.currency)


def validate(name: str, value: Any, condition: bool) -> None:
    """Validates value on condition"""
    assert condition, f'{name} is invalid! ({name}: {value})'


def validate_age(name: str, tolerance: float, from_timestamp: float, to_timestamp: float) -> None:
    """Check if age is valid (within tolerance)"""
    age = to_timestamp - from_timestamp
    assert age <= tolerance, f'{name} is too old! (Age: {age} > Tolerance: {tolerance})'
