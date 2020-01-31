from dataclasses import dataclass, field
from datetime import datetime as dt
from decimal import Decimal
from enum import Enum
from typing import Any, List, Optional, Tuple, Union

import maya
from cached_property import cached_property

from .errors import *
from .money import Money

__all__ = [
    "Number",
    "Money",
    "Market",
    "Side",
    "OrderType",
    "OrderStatus",
    "TxType",
    "TxStatus",
    "Fee",
    "TradingFees",
    "Ticker",
    "Balance",
    "Trade",
    "Order",
    "OrderBookEntry",
    "OrderBook",
    "OrderBookSide",
    "Quotation",
    "Transaction",
    "Withdrawal",
    "Deposit",
]

Number = Union[int, Decimal, Money]


class Market:
    def __init__(self, base: str, quote: str):
        self._base = str(base)
        self._quote = str(quote)

    @property
    def base(self) -> str:
        return self._base

    @property
    def quote(self) -> str:
        return self._quote

    @property
    def code(self) -> str:
        return self.base + self.quote

    @classmethod
    def from_code(cls, code: str):
        assert (
            len(code) == 6
        ), "A market code must have 6 characters (base and quote currency)."
        base, quote = code[:3], code[3:]
        return cls(base, quote)

    def __repr__(self) -> str:
        return self.code

    def __hash__(self) -> int:
        return hash(self.code)

    def __str__(self) -> str:
        return str(self.code)

    def __lt__(self, other: (str, "Market")) -> bool:
        if isinstance(other, Market):
            other = other.code
        return self.code < other

    def __lte__(self, other: (str, "Market")) -> bool:
        if isinstance(other, Market):
            other = other.code
        return self.code <= other

    def __gt__(self, other: (str, "Market")) -> bool:
        if isinstance(other, Market):
            other = other.code
        return self.code > other

    def __gte__(self, other: (str, "Market")) -> bool:
        if isinstance(other, Market):
            other = other.code
        return self.code >= other

    def __eq__(self, other: (str, "Market")) -> bool:
        if isinstance(other, Market):
            other = other.code
        return self.code == other

    def __ne__(self, other: (str, "Market")) -> bool:
        if isinstance(other, Market):
            other = other.code
        return not self.code == other

    def __bool__(self) -> bool:
        return bool(self.code)


class Side(Enum):
    BUY = "buy"
    SELL = "sell"

    def __repr__(self):
        return self.name

    @property
    def type(self) -> str:
        if self == Side.BUY:
            return "bid"
        else:
            return "ask"

    @property
    def reverse(self) -> "Side":
        if self == Side.BUY:
            return Side.SELL
        else:
            return Side.BUY


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"

    def __repr__(self):
        return self.name


class OrderStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELED = "canceled"

    def __repr__(self):
        return self.name


class TxType(Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"

    def __repr__(self):
        return self.name


class TxStatus(Enum):
    OK = "ok"
    FAILED = "failed"
    CANCELED = "canceled"
    PENDING = "pending"

    def __repr__(self):
        return self.name


class Timestamped:
    def __post_init__(self):
        if self.timestamp is None:
            maya_dt = maya.now()
            self.timestamp = maya_dt.epoch
        else:
            maya_dt = maya.MayaDT(self.timestamp)
        if self.datetime is None:
            self.datetime = maya_dt.datetime()
        self.iso8601 = maya_dt.iso8601()


@dataclass
class Fee:
    base: Optional[Money] = None
    percent: Optional[Decimal] = None
    info: Any = field(default=None, repr=False)


@dataclass
class TradingFees:
    maker: Fee
    taker: Fee
    info: Any = field(default=None, repr=False)


@dataclass
class Ticker(Timestamped):
    market: Market
    bid: Money
    ask: Money
    last: Money
    mid: Optional[Money] = field(repr=False)
    open: Optional[Money] = field(repr=False)
    high: Optional[Money] = field(repr=False)
    low: Optional[Money] = field(repr=False)
    close: Optional[Money] = field(repr=False)
    change: Optional[Money] = field(repr=False)
    percentage: Optional[Decimal] = field(repr=False)
    average: Optional[Money] = field(repr=False)
    vwap: Optional[Money] = field(repr=False)
    info: Any = field(default=None, repr=False)
    timestamp: int = field(default=None, repr=False)
    datetime: dt = field(default=None, repr=False)
    iso8601: str = field(default=None, init=False)


@dataclass
class Balance:
    total: Money
    free: Optional[Money]
    used: Optional[Money]
    info: Any = field(default=None, repr=False)


@dataclass
class Trade(Timestamped):
    id: Optional[str]
    market: Market
    type: Optional[OrderType]
    side: Optional[Side]
    amount: Money
    price: Money
    cost: Optional[Money] = field(repr=False)
    fee: Optional[Money] = field(repr=False)
    info: Any = field(default=None, repr=False)
    timestamp: int = field(default=None, repr=False)
    datetime: dt = field(default=None, repr=False)
    iso8601: str = field(default=None, init=False)

    @classmethod
    def create_default(
        cls,
        market: Market,
        amount: Decimal,
        price: Decimal = None,
        timestamp: int = None,
    ) -> "Trade":
        return cls(
            id=None,
            market=market,
            type=None,
            side=None,
            amount=Money(amount, market.base),
            price=Money(price, market.quote),
            cost=None,
            fee=None,
            info=None,
            timestamp=timestamp,
        )


@dataclass
class Order(Timestamped):
    id: Optional[str]
    market: Market
    type: OrderType
    side: Side
    status: Optional[OrderStatus]
    amount: Money
    remaining: Optional[Money] = field(repr=False)
    cost: Optional[Money] = field(repr=False)
    filled: Optional[Money] = field(repr=False)
    fee: Optional[Money] = field(repr=False)
    price: Optional[Money]
    info: Any = field(default=None, repr=False)
    timestamp: int = field(default=None, repr=False)
    datetime: dt = field(default=None, repr=False)
    iso8601: str = field(default=None, init=False)

    @classmethod
    def create_default(
        cls,
        market: Market,
        order_type: OrderType,
        side: Side,
        amount: Decimal,
        price: Decimal = None,
        timestamp: int = None,
    ) -> "Order":
        return cls(
            id=None,
            market=market,
            type=order_type,
            side=side,
            status=None,
            amount=Money(amount, market.base),
            remaining=None,
            filled=None,
            cost=None,
            fee=None,
            price=Money(price, market.quote) if price else None,
            info=None,
            timestamp=timestamp,
        )


@dataclass
class OrderBookEntry:
    price: Money
    amount: Money


OrderBookSide = List[OrderBookEntry]


@dataclass
class Quotation:
    side: Side
    market: Market
    orders: List[OrderBookEntry] = field(repr=False)
    amount: Money = field(repr=False)
    fee: Optional[Decimal] = field(default=None, repr=False)
    amount_other: Money = field(init=False, repr=False)
    base_amount: Money = field(init=False)
    quote_amount: Money = field(init=False)

    def __post_init__(self):
        fee_scalar = Decimal(1) - (self.fee or Decimal(0))
        if self.amount.currency == self.market.base:
            self.amount_other = (
                sum(
                    Money(o.amount.amount * o.price.amount, self.market.quote)
                    for o in self.orders
                )
                * fee_scalar
            )
            self.base_amount, self.quote_amount = self.amount, self.amount_other
        else:
            self.amount_other = (
                sum(
                    Money(o.amount.amount / o.price.amount, self.market.base)
                    for o in self.orders
                )
                * fee_scalar
            )
            self.base_amount, self.quote_amount = self.amount_other, self.amount
        self.average_price = self.quote_amount / self.base_amount.amount

    def __str__(self):
        return f"{self.side} {self.base_amount} for {self.quote_amount} @{self.average_price}"


@dataclass
class OrderBook(Timestamped):
    market: Market
    bids: OrderBookSide = field(repr=False)
    asks: OrderBookSide = field(repr=False)
    info: Any = field(default=None, repr=False)
    timestamp: int = field(default=None, repr=False)
    datetime: dt = field(default=None, repr=False)
    iso8601: str = field(default=None, init=False)

    def __repr__(self):
        name = self.__class__.__qualname__
        return (
            f"{name}("
            + ", ".join(
                [
                    f"market={self.market}",
                    f"bids={len(self.bids)}",
                    f"asks={len(self.asks)}",
                    f"iso8601={self.iso8601}",
                ]
            )
            + ")"
        )

    def get_book_side(self, side: Side) -> OrderBookSide:
        return self.bids if side == Side.BUY else self.asks

    # Volume -----------------------------------------------------------------
    @cached_property
    def volume_bid(self):
        """Get bid volume from order book."""
        return sum(o.amount for o in self.bids)

    @cached_property
    def volume_ask(self):
        """Get ask volume from order book."""
        return sum(o.amount for o in self.asks)

    @cached_property
    def volume(self) -> Money:
        """Get total volume from order book."""
        return self.volume_bid + self.volume_ask

    @cached_property
    def volume_details(self) -> Tuple[Money, Money, Money]:
        """Get volume from order book, returns (total, bid, ask)."""
        volume_bid = self.volume_bid
        volume_ask = self.volume_ask
        volume_total = self.volume
        return volume_total, volume_bid, volume_ask

    # Quote ------------------------------------------------------------------
    def quote(self, side: Side, amount: Money = None, fee: Decimal = None) -> Quotation:
        """Get a quotation for the order book given a side, amount and fee (amount can be base or quote)."""
        orders = self._quote_book_orders(side, amount)
        return Quotation(side, self.market, orders, amount, fee)

    def quote_buy(self, amount: Money = None, fee: Decimal = None) -> Quotation:
        """Get a buy quotation for the order book given an amount and fee (amount can be base or quote)."""
        return self.quote(Side.BUY, amount, fee)

    def quote_sell(self, amount: Money = None, fee: Decimal = None) -> Quotation:
        """Get a sell quotation for the order book given an amount and fee (amount can be base or quote)."""
        return self.quote(Side.SELL, amount, fee)

    def _quote_book_orders(
        self, side: Side, amount: Money = None
    ) -> List[OrderBookEntry]:
        # Flip sides, for a buy quotation we need to quote the sell book (asks)
        side = side.reverse
        orders: List[OrderBookEntry] = []
        order_book_side = self.get_book_side(side)

        if not order_book_side:
            raise OrderBookEmpty(f"{side.value.title()} order book is empty!")
        if amount is None:
            amount = Money(0, self.market.base)
        if amount.currency not in self.market.code:
            raise ValueError(
                f"The amount currency {amount.currency} must be in {self.market}"
            )

        def get_order_amount(order_: OrderBookEntry) -> Money:
            if amount.currency == self.market.quote:
                return order_.price * order_.amount.amount
            return order_.amount

        for order in order_book_side:
            order_amount = min(get_order_amount(order), amount)
            orders.append(OrderBookEntry(order.price, order_amount))
            amount -= order_amount
            if not amount:
                break
        if amount:
            raise QuotationError(
                f"Total amount on {side} order book is not enough to cover quote"
            )
        return orders

    # Spread -----------------------------------------------------------------
    def quote_price(self, side: Side, amount: Money = None) -> Money:
        """Quote price for an amount from a side of the order book."""
        orders = self._quote_book_orders(side, amount)
        return orders[-1].price

    def quote_bid_price(self, amount: Money = None) -> Money:
        """Quote a sell price for an amount from the order book."""
        return self.quote_price(Side.SELL, amount)

    def quote_ask_price(self, amount: Money = None) -> Money:
        """Quote a buy price for an amount from the order book."""
        return self.quote_price(Side.BUY, amount)

    def quote_spread_details(self, amount: Money = None) -> Tuple[Money, Money, Money]:
        """Quote spread details (bid, ask, spread) for an amount from the order book."""
        bid = self.quote_bid_price(amount)
        ask = self.quote_ask_price(amount)
        spread = ask - bid
        return bid, ask, spread

    def quote_spread(self, amount: Money = None) -> Money:
        """Quote the spread for an amount from the order book."""
        bid, ask, spread = self.quote_spread_details(amount)
        return spread

    @cached_property
    def spread_details(self) -> Tuple[Money, Money, Money]:
        """Get the spread details (bid, ask, spread) for an amount from the order book."""
        return self.quote_spread_details()

    @cached_property
    def spread(self) -> Money:
        """Get the spread from order book."""
        return self.quote_spread()

    @cached_property
    def bid_price(self) -> Money:
        """Get the bid price from order book."""
        return self.quote_ask_price()

    @cached_property
    def ask_price(self) -> Money:
        """Get the ask price from order book."""
        return self.quote_bid_price()

    @cached_property
    def vw_price(self) -> Money:
        """Get the volume-weighted price from order book."""
        volume_total, volume_bid, volume_ask = self.volume_details
        bid, ask, spread = self.spread_details
        if volume_total:
            sum_prod = volume_bid.amount * bid.amount + volume_ask.amount * ask.amount
            vw_price = Money(sum_prod / volume_total.amount, self.market.quote)
        else:
            vw_price = None
        return vw_price


@dataclass
class Transaction(Timestamped):
    id: Optional[Union[str, int]]
    type: TxType
    currency: str
    amount: Money
    status: Optional[TxStatus]
    address: Optional[str]
    tx_hash: Optional[str] = field(repr=False)
    fee: Optional[Money] = field(repr=False)
    info: Any = field(default=None, repr=False)
    timestamp: int = field(default=None, repr=False)
    datetime: dt = field(default=None, repr=False)
    iso8601: str = field(default=None, init=False)

    @classmethod
    def create_default(
        cls,
        tx_type: TxType,
        currency: str,
        amount: Decimal,
        address: str,
        timestamp=timestamp,
    ) -> "Transaction":
        return cls(
            id=None,
            type=tx_type,
            currency=currency,
            amount=Money(amount, currency),
            status=None,
            address=address,
            tx_hash=None,
            fee=None,
            info=None,
            timestamp=timestamp,
        )


Withdrawal = Transaction
Deposit = Transaction
