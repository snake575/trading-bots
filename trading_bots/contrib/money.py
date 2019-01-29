from decimal import Decimal
from typing import Union, Tuple

__all__ = [
    'Money',
    'InvalidAmountError',
    'CurrencyMismatchError',
    'InvalidOperandError',
]

Number = Union[int, Decimal]


class InvalidAmountError(ValueError):
    def __init__(self):
        super().__init__('Invalid amount for currency')


class CurrencyMismatchError(ValueError):
    def __init__(self):
        super().__init__('Currencies must match')


class InvalidOperandError(ValueError):
    def __init__(self):
        super().__init__('Invalid operand types for operation')


class Money:
    """Class representing a monetary amount"""

    def __init__(self, amount: Union[str, int, Decimal], currency: str) -> None:
        self._amount = Decimal(amount)
        self._currency = currency.upper()

    @property
    def amount(self) -> Decimal:
        """Returns the numeric amount"""
        return self._amount

    @property
    def currency(self) -> str:
        """Returns the currency"""
        return self._currency

    def __hash__(self) -> int:
        return hash((self._amount, self._currency))

    def __repr__(self) -> str:
        return f'{self._currency} {self._amount}'

    def __str__(self) -> str:
        return f'{self._amount:,f} {self._currency}'

    def __lt__(self, other: 'Money') -> bool:
        if not isinstance(other, Money):
            raise InvalidOperandError
        self._assert_same_currency(other)
        return self._amount < other.amount

    def __le__(self, other: 'Money') -> bool:
        if not isinstance(other, Money):
            raise InvalidOperandError
        self._assert_same_currency(other)
        return self._amount <= other.amount

    def __gt__(self, other: 'Money') -> bool:
        if not isinstance(other, Money):
            raise InvalidOperandError
        self._assert_same_currency(other)
        return self._amount > other.amount

    def __ge__(self, other: 'Money') -> bool:
        if not isinstance(other, Money):
            raise InvalidOperandError
        self._assert_same_currency(other)
        return self._amount >= other.amount

    def __eq__(self, other: 'Money') -> bool:
        if not isinstance(other, Money):
            raise InvalidOperandError
        self._assert_same_currency(other)
        return self._amount == other.amount

    def __ne__(self, other: 'Money') -> bool:
        return not self == other

    def __bool__(self):
        return bool(self._amount)

    def __add__(self, other: Union[Number, 'Money']) -> 'Money':
        if isinstance(other, Money):
            self._assert_same_currency(other)
            other = other.amount
        amount = self._amount + other
        return self.__class__(amount, self.currency)

    __radd__ = __add__

    def __sub__(self, other: Union[Number, 'Money']) -> 'Money':
        if isinstance(other, Money):
            self._assert_same_currency(other)
            other = other.amount
        amount = self._amount - other
        return self.__class__(amount, self.currency)

    __rsub__ = __sub__

    def __mul__(self, other: Number) -> 'Money':
        if isinstance(other, Money):
            raise InvalidOperandError
        amount = self._amount * other
        return self.__class__(amount, self._currency)

    __rmul__ = __mul__

    def __truediv__(self, other: Union[Number, 'Money']) -> Union[Decimal, 'Money']:
        if isinstance(other, Money):
            self._assert_same_currency(other)
            if other.amount == 0:
                raise ZeroDivisionError
            return self._amount / other.amount
        else:
            if other == 0:
                raise ZeroDivisionError
            amount = self._amount / other
            return self.__class__(amount, self._currency)

    def __floordiv__(self, other: Union[Number, 'Money']) -> Union[Decimal, 'Money']:
        if isinstance(other, Money):
            self._assert_same_currency(other)
            if other.amount == 0:
                raise ZeroDivisionError
            return self._amount // other.amount
        else:
            if other == 0:
                raise ZeroDivisionError
            amount = self._amount // other
            return self.__class__(amount, self._currency)

    def __mod__(self, other: Union[Number, 'Money']) -> Union[Decimal, 'Money']:
        if isinstance(other, Money):
            self._assert_same_currency(other)
            if other.amount == 0:
                raise ZeroDivisionError
            return self.amount % other.amount
        else:
            if other == 0:
                raise ZeroDivisionError
            amount = self._amount % other
            return self.__class__(str(amount), self._currency)

    def __divmod__(self, other: Union[Number, 'Money']) -> Tuple:
        if isinstance(other, Money):
            self._assert_same_currency(other)
            if other.amount == 0:
                raise ZeroDivisionError()
            return divmod(self._amount, other.amount)
        else:
            if other == 0:
                raise ZeroDivisionError()
            whole, remainder = divmod(self._amount, other)
            return (self.__class__(whole, self._currency),
                    self.__class__(remainder, self._currency))

    def __pow__(self, other: Number) -> 'Money':
        if isinstance(other, Money):
            raise TypeError("power operator is unsupported between two '{}' "
                            "objects".format(self.__class__.__name__))
        amount = self._amount ** other
        return self.__class__(amount, self._currency)

    def __neg__(self) -> 'Money':
        return self.__class__(-self._amount, self._currency)

    def __pos__(self) -> 'Money':
        return self.__class__(+self._amount, self._currency)

    def __abs__(self) -> 'Money':
        return self.__class__(abs(self._amount), self._currency)

    def __int__(self) -> int:
        return int(self._amount)

    def __float__(self) -> float:
        return float(self._amount)

    def __round__(self, n_digits: int=0) -> 'Money':
        return self.__class__(round(self._amount, n_digits), self._currency)

    def __trunc__(self) -> 'Money':
        return self.__class__(int(self._amount), self._currency)

    def __composite_values__(self) -> Tuple:
        return self._amount, self._currency

    def _assert_same_currency(self, other: 'Money') -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError

    @classmethod
    def loads(cls, s: str) -> 'Money':
        """Parse from a string representation (repr)"""
        try:
            currency, amount = s.strip().split()
            return cls(amount, currency)
        except ValueError as err:
            raise ValueError("failed to parse string "
                             " '{}': {}".format(s, err))
