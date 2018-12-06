import abc
from decimal import Decimal
from functools import wraps
from logging import Logger
from operator import attrgetter
from typing import Any, Dict, Callable, List, Optional, Set, Type, Tuple, Union

import maya
from cached_property import cached_property
from requests_toolbelt import user_agent

from trading_bots.__version__ import __version__
from trading_bots.conf import settings
from trading_bots.core.logging import get_logger
from trading_bots.core.storage import Store
from trading_bots.core.storage import get_store
from .errors import *
from .models import *
from .utils import parse_money

__all__ = [
    'USER_AGENT',
    'ClientWrapper',
    'BaseClient',
    'MarketClient',
    'WalletClient',
    'TradingClient'
]

USER_AGENT = user_agent('trading-bots', __version__)


class ClientWrapper(abc.ABC):
    name: str = None

    def __init__(self, client_params: Dict=None, name: str=None):
        assert self.name, 'A name must be defined for the client!'
        credentials = getattr(settings, 'credentials', {})
        self.credentials: Dict = credentials.get(self.name, {})
        self.timeout: int = getattr(settings, 'timeout')
        self.client_params: Dict = self._build_client_params(**client_params or {})
        if name is not None:
            self.name = name

    def _build_client_params(self, **params) -> Dict:
        return {'timeout': self.timeout, 'user_agent': USER_AGENT, **params}


class BaseClient(ClientWrapper, abc.ABC):

    def __init__(self, client_params: Dict=None, dry_run: bool=False,
                 logger: Logger=None, store: Store=None, name: str=None, **kwargs):
        super().__init__(client_params, name)
        self.dry_run: bool = dry_run
        self.log: Logger = logger or get_logger(__name__)
        self.store = store or get_store(self.log)

    common_currencies = {
        'XBT': 'BTC',
        'BCC': 'BCH',
        'DRK': 'DASH',
    }

    def _parse_common_currency(self, currency: str) -> str:
        return self.common_currencies.get(currency, currency)

    @cached_property
    @abc.abstractmethod
    def client(self):
        pass

    @abc.abstractmethod
    def _markets(self) -> Set[Market]:
        pass

    @cached_property
    def markets(self) -> Set[Market]:
        """Fetch supported markets."""
        return self._fetch('Markets')(self._markets)()

    def _currencies(self) -> Set[str]:
        markets = self._markets()
        return {*{market.base for market in markets},
                *{market.quote for market in markets}}

    @cached_property
    def currencies(self) -> Set[str]:
        """Fetch supported currencies."""
        return self._fetch('Currencies')(self._currencies)()

    def exception(self, exc_type: Type[Exception]=None, msg: str=None, exc: Exception=None) -> Exception:
        if exc_type is None:
            exc_type = ExchangeError
        if isinstance(exc, (ExchangeError, NotImplementedError)):
            return exc
        return exc_type(msg)

    def check_credentials(self):
        if not self.credentials:
            raise self.exception(AuthenticationError, f'{self.name} credentials not set!')
        for key, value in self.credentials.items():
            if not value:
                raise self.exception(AuthenticationError, f'{self.name} requires `{key}`')

    @staticmethod
    def safe_money(value: Dict, key: str, currency: str) -> Optional[Money]:
        amount = value.get(key)
        if amount:
            return Money(amount, currency)

    @staticmethod
    def _filter_limit(entries: List, limit: int=None) -> List:
        if limit:
            return entries[:limit]
        return entries

    @staticmethod
    def _filter_since(entries: List, since: int) -> List:
        return [entry for entry in entries if entry.timestamp >= since]

    @staticmethod
    def _sort_timestamp(entries: List, reverse=True) -> List:
        return sorted(entries, key=attrgetter('timestamp'), reverse=reverse)

    def _fetch(self, entity: str, prefix: str=None, suffix: str=None, exc: Type[Exception]=None):
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Log fetching
                msg = f'{entity} on {self.name}'
                if prefix:
                    msg = f'{prefix} {msg}'
                if suffix:
                    msg = f'{msg} {suffix}'

                try:  # Perform fetch
                    result = func(*args, **kwargs)
                except Exception as e:
                    raise self.exception(exc, f'Failed fetching {msg}!', e) from e

                # Log result
                if isinstance(result, (list, set, tuple)):
                    result_msg = len(result)
                else:
                    result_msg = str(result)
                self.log.debug(f'{msg}: {result_msg}')

                return result

            return wrapper
        return decorator

    def _fetch_limit(self, entity: str, prefix: str, exc: Type[Exception]=None):
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(limit: int=None):
                suffix = f'(limit={limit})' if limit else '(all)'
                return self._fetch(entity, prefix, suffix, exc)(func)(limit)
            return wrapper
        return decorator

    def _fetch_since(self, entity: str, prefix: str, exc: Type[Exception]=None):
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(since: int):
                maya_dt = maya.MayaDT(since)
                rfc2822 = maya_dt.rfc2822()
                slang = maya_dt.slang_time()
                suffix = f'since {rfc2822} ({slang})'
                return self._fetch(entity, prefix, suffix, exc)(func)(since)
            return wrapper
        return decorator


class MarketClient(BaseClient, abc.ABC):

    def __init__(self, market: Union[str, Market], client_params: Dict=None, dry_run: bool=False,
                 logger: Logger=None, store: Store=None, name: str=None, **kwargs):
        super().__init__(client_params, dry_run, logger, store, name, **kwargs)
        if not isinstance(market, Market):
            market = Market.from_code(market)
        self.market: Market = market
        self.market_id: str = self._market_id()

    def __repr__(self):
        return f'MarketClient({self.name})'

    def _market_id(self) -> str:
        return self.market.code

    def _parse_base(self, value: Number) -> Optional[Decimal]:
        return parse_money(value, self.market.base)

    def _parse_quote(self, value: Number) -> Optional[Decimal]:
        return parse_money(value, self.market.quote)

    @abc.abstractmethod
    def _ticker(self) -> Ticker:
        pass

    def fetch_ticker(self) -> Ticker:
        """Fetch the market ticker."""
        return self._fetch('ticker', self.market.code)(self._ticker)()

    @abc.abstractmethod
    def _order_book(self) -> OrderBook:
        pass

    def _parse_order_book_entry(self, order: Tuple[str, str]) -> OrderBookEntry:
        return OrderBookEntry(
            price=Money(order[0], self.market.quote),
            amount=Money(order[1], self.market.base),
        )

    def _parse_order_book(self, order_book: Dict) -> OrderBook:
        return OrderBook(
            market=self.market,
            bids=[self._parse_order_book_entry(entry) for entry in order_book['bids']],
            asks=[self._parse_order_book_entry(entry) for entry in order_book['asks']],
            info=order_book,
        )

    def fetch_order_book(self) -> OrderBook:
        """Fetch the order book."""
        return self._fetch('order book', self.market.code)(self._order_book)()

    # Trades
    @abc.abstractmethod
    def _trades_since(self, since: int) -> List[Trade]:
        pass

    def fetch_trades_since(self, since: int) -> List[Trade]:
        """Fetch trades since given timestamp."""
        return self._fetch_since('trades', self.market.code)(self._trades_since)(since)

    @abc.abstractmethod
    def _parse_trade(self, trade: Any) -> Trade:
        pass

    def _parse_trades(self, trades: List, since: int) -> List[Trade]:
        return self._sort_timestamp(self._filter_since([self._parse_trade(trade) for trade in trades], since))


class WalletClient(BaseClient, abc.ABC):
    withdrawal_fees = {}

    def __init__(self, currency: str, client_params: Dict=None, dry_run: bool=False,
                 logger: Logger=None, store: Store=None, name: str=None, **kwargs):
        super().__init__(client_params, dry_run, logger, store, name, **kwargs)
        self.currency: str = currency.upper()
        self.currency_id: str = self._currency_id()

    def __repr__(self):
        return f'WalletClient({self.name})'

    def _currency_id(self) -> str:
        return self.currency

    def _parse_money(self, value: Number) -> Optional[Decimal]:
        return parse_money(value, self.currency)

    # Balance
    @abc.abstractmethod
    def _balance(self) -> Balance:
        pass

    def fetch_balance(self) -> Balance:
        """Fetch wallet balance total, free and used amounts."""
        return self._fetch('balance', self.currency)(self._balance)()

    # Transactions
    def _transactions(self, func: Callable, tx_name: str, limit: int=None) -> List[Transaction]:
        return self._fetch_limit(tx_name, self.currency)(func)(limit)

    def _transactions_since(self, func: Callable, tx_name: str, since: int) -> List[Transaction]:
        return self._fetch_since(tx_name, self.currency)(func)(since)

    # Transactions: Deposits
    @abc.abstractmethod
    def _deposits(self, limit: int=None) -> List[Deposit]:
        pass

    def fetch_deposits(self, limit: int) -> List[Deposit]:
        """Fetch latest deposits, must provide a limit."""
        return self._transactions(self._deposits, 'deposits', limit)

    def fetch_all_deposits(self) -> List[Deposit]:
        """Fetch all deposits."""
        return self._transactions(self._deposits, 'deposits', limit=None)

    @abc.abstractmethod
    def _deposits_since(self, since: int) -> List[Deposit]:
        pass

    def fetch_deposits_since(self, since: int) -> List[Deposit]:
        """Fetch all deposits since the given timestamp."""
        return self._transactions_since(self._deposits_since, 'deposits', since)

    # Transactions: Withdrawals
    @abc.abstractmethod
    def _withdrawals(self, limit: int=None) -> List[Withdrawal]:
        pass

    def fetch_withdrawals(self, limit: int) -> List[Withdrawal]:
        """Fetch latest withdrawals, must provide a limit."""
        return self._transactions(self._withdrawals, 'withdrawals', limit)

    def fetch_all_withdrawals(self) -> List[Withdrawal]:
        """Fetch all withdrawals."""
        return self._transactions(self._withdrawals, 'withdrawals', limit=None)

    @abc.abstractmethod
    def _withdrawals_since(self, since: int) -> List[Withdrawal]:
        pass

    def fetch_withdrawals_since(self, since: int) -> List[Withdrawal]:
        """Fetch all withdrawals since the given timestamp."""
        return self._transactions_since(self._withdrawals_since, 'withdrawals', since)

    # Transfers: Request withdrawal
    @cached_property
    def withdrawal_fee(self) -> Money:
        """Withdrawal fee on request."""
        try:
            return self.withdrawal_fees[self.currency]
        except KeyError:
            return Money(0, self.currency)

    @abc.abstractmethod
    def _withdraw(self, amount: Decimal, address: str, subtract_fee: bool=False, **params) -> Withdrawal:
        pass

    def request_withdrawal(self, amount: Number, address: str, subtract_fee: bool=False, **params) -> Withdrawal:
        """Request a withdrawal."""
        self.log.debug(f'Requesting {self.currency} withdrawal from {self.name} to {address}')
        amount = self._parse_money(amount)

        if self.dry_run:
            withdrawal = Withdrawal.create_default(TxType.WITHDRAWAL, self.currency, amount, address)
            self.log.warning(f'DRY RUN: Withdrawal requested on {self.name}: {withdrawal}')
            return withdrawal

        try:
            withdrawal = self._withdraw(amount, address, subtract_fee, **params)
        except Exception as e:
            msg = f'Failed requesting withdrawal on {self.name}!: amount={amount}, address={address}'
            raise self.exception(InvalidWithdrawal, msg, e) from e

        self.log.info(f'Withdrawal requested on {self.name}: {withdrawal}')
        return withdrawal

    @abc.abstractmethod
    def _parse_transaction(self, tx: Any, tx_type: TxType) -> Transaction:
        pass

    def _filter_currency(self, txs: List[Transaction]) -> List[Transaction]:
        return [tx for tx in txs if tx.currency == self.currency]

    def _parse_transactions(self, txs: List, tx_type: TxType):
        def wrapper(filter_func: Callable, *filter_args) -> List[Transaction]:
            parsed_txs = [self._parse_transaction(tx, tx_type) for tx in txs]
            return self._sort_timestamp(filter_func(self._filter_currency(parsed_txs), *filter_args))
        return wrapper

    def _parse_transactions_limit(self, txs: List, tx_type: TxType, limit: int=None) -> List[Transaction]:
        return self._parse_transactions(txs, tx_type)(self._filter_limit, limit)

    def _parse_transactions_since(self, txs: List, tx_type: TxType, since: int) -> List[Transaction]:
        return self._parse_transactions(txs, tx_type)(self._filter_since, since)


class TradingClient(MarketClient, abc.ABC):
    has_batch_cancel: bool = False
    min_order_amount_mapping: Dict[str, Decimal] = {}
    _wallet_cls: Type[WalletClient] = None

    class Wallets:
        def __init__(self, cls: Type[WalletClient], market: Market, client_params: Dict,
                     dry_run: bool, logger: Logger, store: Store, name: str, **kwargs):
            self.base: WalletClient = cls(market.base, client_params, dry_run, logger, store, name, **kwargs)
            self.quote: WalletClient = cls(market.quote, client_params, dry_run, logger, store, name, **kwargs)

    def __init__(self, market: Union[str, Market], client_params: Dict=None, dry_run: bool=False,
                 logger: Logger=None, store: Store=None, name: str=None, **kwargs):
        super().__init__(market, client_params, dry_run, logger, store, name, **kwargs)
        assert self._wallet_cls, 'A wallet cls must be defined for the client!'
        self.wallets = self.Wallets(self._wallet_cls, self.market, self.client_params,
                                    self.dry_run, self.log, self.store, self.name, **kwargs)

    def __repr__(self):
        return f'TradingClient({self.name})'

    @abc.abstractmethod
    def _order(self, order_id: str) -> Order:
        pass

    def fetch_order(self, order_id: str) -> Order:
        """Fetch an order by ID."""
        return self._fetch(f'order id={order_id}', exc=OrderNotFound)(self._order)(order_id)

    def _fetch_orders_limit(self, func: Callable, limit: int=None) -> List[Order]:
        return self._fetch_limit('orders', self.market.code)(func)(limit)

    def _fetch_orders_since(self, func: Callable, since: int) -> List[Order]:
        return self._fetch_since('orders', self.market.code)(func)(since)

    @abc.abstractmethod
    def _open_orders(self, limit: int=None) -> List[Order]:
        pass

    def fetch_open_orders(self, limit: int) -> List[Order]:
        """Fetch latest open orders, must provide a limit."""
        return self._fetch_orders_limit(self._open_orders, limit)

    def fetch_all_open_orders(self) -> List[Order]:
        """Fetch all open orders."""
        return self._fetch_orders_limit(self._open_orders, limit=None)

    @abc.abstractmethod
    def _closed_orders(self, limit: int=None) -> List[Order]:
        pass

    def fetch_closed_orders(self, limit: int) -> List[Order]:
        """Fetch latest closed orders, must provide a limit."""
        return self._fetch_orders_limit(self._closed_orders, limit)

    def fetch_all_closed_orders(self) -> List[Order]:
        """Fetch all closed orders."""
        return self._fetch_orders_limit(self._closed_orders, limit=None)

    @abc.abstractmethod
    def _closed_orders_since(self, since: int) -> List[Order]:
        pass

    def fetch_closed_orders_since(self, since: int) -> List[Order]:
        """Fetch closed orders since the given timestamp."""
        return self._fetch_orders_since(self._closed_orders_since, since)

    @abc.abstractmethod
    def _cancel_order(self, order_id: str) -> None:
        pass

    def cancel_order(self, order_id: str) -> str:
        """Cancel an order by ID."""
        self.log.debug(f'Canceling order id={order_id} on {self.name}')

        if self.dry_run:  # Don't cancel if dry run
            self.log.warning(f'DRY RUN: Order cancelled on {self.name}: id={order_id}')
            return order_id

        try:  # Cancel order
            self._cancel_order(order_id)
        except Exception as e:
            raise self.exception(OrderNotFound, f'Failed to cancel order: id={order_id}', e) from e

        self.log.info(f'Order cancelled on {self.name}: id={order_id}')
        return order_id

    @abc.abstractmethod
    def _cancel_orders(self, order_ids: List[str]=None) -> None:
        pass

    def cancel_orders(self, order_ids: List[str]) -> List[str]:
        """Cancel multiple orders by a list of IDs."""
        orders_to_cancel = order_ids
        self.log.debug(f'Canceling orders on {self.name}: ids={orders_to_cancel}')
        cancelled_orders = []

        if self.dry_run:  # Don't cancel if dry run
            self.log.warning(f'DRY RUN: Orders cancelled on {self.name}: {orders_to_cancel}')
            return orders_to_cancel

        try:  # Iterate and cancel orders
            if self.has_batch_cancel:
                self._cancel_orders(orders_to_cancel)
                cancelled_orders.append(orders_to_cancel)
                orders_to_cancel.clear()
            else:
                for i, order_id in enumerate(orders_to_cancel):
                    self._cancel_order(order_id)
                    cancelled_orders.append(order_id)
                    orders_to_cancel.pop(i)
        except Exception as e:
            msg = f'Failed to cancel {len(orders_to_cancel)} orders on {self.name}: ids={orders_to_cancel}'
            raise self.exception(OrderNotFound, msg, e) from e

        self.log.info(f'Orders cancelled on {self.name}: ids={cancelled_orders}')
        return cancelled_orders

    def cancel_all_orders(self) -> List[str]:
        """Cancel all open orders."""
        order_ids = [o.id for o in self.fetch_all_open_orders()]
        return self.cancel_orders(order_ids)

    @cached_property
    def min_order_amount(self) -> Money:
        """Minimum amount to place an order."""
        try:
            amount = self.min_order_amount_mapping[self.market.base]
        except KeyError:
            amount = 0
        return Money(amount, self.market.base)

    @abc.abstractmethod
    def _place_order(self, side: Side, order_type: OrderType, amount: Decimal, price: Decimal=None) -> Order:
        pass

    def place_order(self, side: Side, order_type: OrderType, amount: Number, price: Number=None) -> Order:
        """Place an order."""
        order_repr = f'side={side} type={order_type} amount={amount} price={price}'
        order_err = f'Failed to place order on {self.name}!: {order_repr}'

        self.log.debug(f'Placing order on {self.name}: {order_repr}')
        amount = self._parse_base(amount)
        price = self._parse_quote(price)

        min_amount = self.min_order_amount.amount  # Don´t place order if the amount < min allowed
        if min_amount and amount < min_amount:
            msg = f'{order_err}\n> Reason: amount={amount} < min_amount={min_amount}'
            raise self.exception(OrderTooSmall, msg)

        if self.dry_run:  # Don't place order if dry run
            order = Order.create_default(self.market, order_type, side, amount, price)
            self.log.warning(f'DRY RUN: Order placed: {order}')
            return order

        try:  # Place order
            order = self._place_order(side, order_type, amount, price)
        except Exception as e:
            raise self.exception(OrderNotPlaced, order_err, e) from e

        self.log.info(f'Order placed on {self.name}: {order}')
        return order

    def place_market_order(self, side: Side, amount: Number) -> Order:
        """Place a market order."""
        return self.place_order(side, OrderType.MARKET, amount)

    def place_limit_order(self, side: Side, amount: Number, price: Number) -> Order:
        """Place a limit order."""
        return self.place_order(side, OrderType.LIMIT, amount, price)

    @abc.abstractmethod
    def _parse_order(self, order: Any) -> Order:
        pass

    def _filter_market(self, orders: List[Order]) -> List[Order]:
        return [o for o in orders if o.market == self.market]

    def _parse_orders(self, orders: List):
        def wrapper(filter_func: Callable, *filter_args) -> List[Order]:
            parsed_orders = list(map(self._parse_order, orders))
            return self._sort_timestamp(filter_func(self._filter_market(parsed_orders), *filter_args))
        return wrapper

    def _parse_orders_limit(self, orders: List, limit: int=None) -> List[Order]:
        return self._parse_orders(orders)(self._filter_limit, limit)

    def _parse_orders_since(self, orders: List, since: int) -> List[Order]:
        return self._parse_orders(orders)(self._filter_since, since)
