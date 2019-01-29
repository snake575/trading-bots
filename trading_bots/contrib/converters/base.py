import abc
from decimal import Decimal
from typing import Dict, Union

from trading_bots.core.logging import get_logger
from ..clients import ClientWrapper
from ..money import Money

__all__ = [
    'ConverterRateError',
    'ConverterValidationError',
    'Converter'
]

logger = get_logger(__name__)
Number = Union[float, Decimal]


class ConverterRateError(Exception):
    def __init__(self, converter):
        super().__init__(f'{converter} failed to get rate!')


class ConverterValidationError(Exception):
    def __init__(self, converter, rate):
        super().__init__(f'{converter} rate is invalid!: {rate}')


class Converter(ClientWrapper, abc.ABC):

    def __init__(self, return_decimal: bool=False, client_params: Dict=None, name: str=None):
        super().__init__(client_params, name)
        self.return_decimal = return_decimal

    def _format_number(self, value: (str, Number)) -> Number:
        if self.return_decimal:
            if not isinstance(value, Decimal):
                return Decimal(value)
        return float(value)

    @abc.abstractmethod
    def _get_rate(self, currency: str, to: str) -> Union[str, Number]:
        pass

    def get_rate_for(self, currency: str, to: str, reverse: bool=False) -> Number:
        """Get current market rate for currency"""

        # Return 1 when currencies match
        if currency.upper() == to.upper():
            return self._format_number('1.0')

        # Set base and quote currencies
        base, quote = currency, to
        if reverse:
            base, quote = to, currency

        try:  # Get rate from source
            rate = self._get_rate(base, quote)
        except Exception as e:
            raise ConverterRateError(self.name) from e

        # Convert rate to number
        rate = self._format_number(rate)

        try:  # Validate rate value
            assert isinstance(rate, (float, Decimal))
            assert rate > 0
        except AssertionError as e:
            raise ConverterValidationError(self.name, rate) from e

        # Return market rate
        if reverse:
            return self._format_number('1.0') / rate
        return rate

    def convert(self, amount: Number, currency: str, to: str, reverse: bool=False) -> Number:
        """Convert amount to another currency"""
        rate = self.get_rate_for(currency, to, reverse)
        if self.return_decimal:
            amount = Decimal(amount)
        return amount * rate

    def convert_money(self, money: Money, to: str, reverse: bool=False) -> Money:
        """Convert money to another currency"""
        converted = self.convert(money.amount, money.currency, to, reverse)
        return Money(converted, to)
