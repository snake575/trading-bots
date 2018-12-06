from abc import ABC
from decimal import Decimal
from functools import wraps
from typing import List, Optional, Set

import maya
from cached_property import cached_property
from trading_api_wrappers import Buda

from ...clients import *
from ...errors import *
from ...models import *

__all__ = [
    'BudaBase',
    'BudaPublic',
    'BudaAuth',
    'BudaMarket',
    'BudaWallet',
    'BudaTrading',
]

PER_PAGE = 300


def paginated_limit(data_attr: str, max_limit: int):
    def decorator(func):
        @wraps(func)
        def wrapper(limit: int=None, **kwargs):
            data = []
            page = 1
            per_page = min(limit, max_limit) if limit else max_limit
            while True:
                paginated_data = func(page, per_page, **kwargs)
                new_data = getattr(paginated_data, data_attr)
                data.extend(new_data)
                page = paginated_data.meta.current_page + 1
                is_last_page = page > paginated_data.meta.total_pages
                if is_last_page or (limit and len(data) == limit):
                    return data
        return wrapper
    return decorator


def paginated_since(data_attr: str, max_limit: int):
    def decorator(func):
        @wraps(func)
        def wrapper(since: int, **kwargs):
            data = []
            page = 1
            per_page = max_limit
            while True:
                paginated_data = func(page, per_page, **kwargs)
                new_data = getattr(paginated_data, data_attr)
                data.extend(new_data)
                page = paginated_data.meta.current_page + 1
                is_last_page = page > paginated_data.meta.total_pages
                if is_last_page or new_data[-1].created_at.timestamp() <= since:
                    return data
        return wrapper
    return decorator


class BudaBase(BaseClient, ABC):
    name = 'Buda'

    def _markets(self) -> Set[Market]:
        markets = self.client.markets()
        return {Market(*market.id.split('-')) for market in markets}

    def _currencies(self) -> Set[str]:
        response = self.client.get('currencies')
        return {ccy['id'] for ccy in response['currencies'] if ccy['managed']}


class BudaPublic(BudaBase):

    @cached_property
    def client(self) -> Buda.Public:
        return Buda.Public(**self.client_params)


class BudaAuth(BudaBase):

    @cached_property
    def client(self) -> Buda.Auth:
        self.check_credentials()
        return Buda.Auth(**self.credentials, **self.client_params)


class BudaMarketBase(MarketClient, ABC):

    def _market_id(self) -> str:
        return f'{self.market.base}-{self.market.quote}'.lower()

    def _ticker(self) -> Ticker:
        ticker = self.client.ticker(self.market_id)
        return self._parse_ticker(ticker)

    def _parse_ticker(self, ticker: Buda.models.Ticker) -> Ticker:
        last = Money(*ticker.json['last_price'])
        percentage = Decimal(ticker.json['price_variation_24h'])
        open_ = last / (percentage + 1)
        change = last - open_
        average = (last + open_) / 2
        return Ticker(
            market=self.market,
            bid=Money(*ticker.json['max_bid']),
            ask=Money(*ticker.json['min_ask']),
            last=last,
            open=None,
            high=None,
            low=None,
            close=last,
            change=change,
            percentage=percentage,
            average=average,
            vwap=None,
            info=ticker,
        )

    def _order_book(self) -> OrderBook:
        response = self.client.order_book(self.market_id)
        order_book = self._parse_order_book(response.json)
        order_book.info = response
        return order_book

    def _trades_since(self, since: int) -> List[Trade]:

        def get_trades():
            data = []
            timestamp = None
            max_limit = PER_PAGE
            while True:
                response = self.client.trades(self.market_id, timestamp=timestamp, limit=max_limit)
                timestamp = response.last_timestamp
                entries = response.entries
                data.extend(entries)
                if not entries or timestamp / 1000 <= since:
                    return data

        trades = get_trades()
        return self._parse_trades(trades, since)

    def _parse_trade(self, trade: Buda.models.TradeEntry):
        maya_dt = maya.MayaDT(trade.timestamp / 1000)
        return Trade(
            id=None,
            market=self.market,
            type=None,
            side=Side(trade.direction),
            amount=Money(str(trade.amount), self.market.base),
            price=Money(str(trade.price), self.market.quote),
            cost=Money(str(trade.amount * trade.price), self.market.quote),
            fee=None,
            info=trade,
            timestamp=maya_dt.epoch,
            datetime=maya_dt.datetime(),
        )


class BudaMarket(BudaMarketBase, BudaPublic):
    pass


class BudaWallet(WalletClient, BudaAuth):
    states_mapping = {
        TxStatus.OK: ('confirmed',),
        TxStatus.PENDING: ('pending',),
        TxStatus.FAILED: ('rejected',),
        TxStatus.CANCELED: ('anulled', 'retained'),
    }

    def _balance(self) -> Balance:
        balance = self.client.balance(self.currency)
        total = Money(*balance.json['amount'])
        free = Money(*balance.json['available_amount'])
        return Balance(
            total=total,
            free=free,
            used=total - free,
            info=balance,
        )

    def _deposits(self, limit: int=None) -> List[Deposit]:
        @paginated_limit('deposits', PER_PAGE)
        def fetch_deposits(page, per_page):
            return self.client.deposit_pages(self.currency, page=page, per_page=per_page)
        deposits = fetch_deposits(limit)
        return self._parse_transactions_limit(deposits, TxType.DEPOSIT, limit)

    def _deposits_since(self, since: int) -> List[Deposit]:
        @paginated_since('deposits', PER_PAGE)
        def fetch_deposits(page, per_page):
            return self.client.deposit_pages(self.currency, page=page, per_page=per_page)
        deposits = fetch_deposits(since)
        return self._parse_transactions_since(deposits, TxType.DEPOSIT, since)

    def _withdrawals(self, limit: int=None) -> List[Withdrawal]:
        @paginated_limit('withdrawals', PER_PAGE)
        def fetch_withdrawals(page, per_page):
            return self.client.withdrawal_pages(self.currency, page=page, per_page=per_page)
        withdrawals = fetch_withdrawals(limit)
        return self._parse_transactions_limit(withdrawals, TxType.WITHDRAWAL, limit)

    def _withdrawals_since(self, since: int) -> List[Withdrawal]:
        @paginated_since('withdrawals', PER_PAGE)
        def fetch_withdrawals(page, per_page):
            return self.client.withdrawal_pages(self.currency, page=page, per_page=per_page)
        withdrawals = fetch_withdrawals(since)
        return self._parse_transactions_since(withdrawals, TxType.WITHDRAWAL, since)

    def _withdraw(self, amount: Decimal, address: str, subtract_fee: bool=False, **params) -> Withdrawal:
        if self.dry_run:
            withdrawal = self.client.simulate_withdrawal(
                self.currency, float(amount), amount_includes_fee=subtract_fee, **params)
        else:
            withdrawal = self.client.withdrawal(
                self.currency, float(amount), address, amount_includes_fee=subtract_fee, **params)
        return self._parse_transaction(withdrawal, TxType.WITHDRAWAL)

    def _parse_tx_status(self, state: str) -> Optional[TxStatus]:
        if 'pending' in state:
            return TxStatus.PENDING
        for status, mappings in self.states_mapping.items():
            if state in mappings:
                return status

    def _parse_transaction(self, tx: Buda.models.Transfer, tx_type: TxType) -> Transaction:
        data = tx.data
        created_at = tx.created_at
        return Transaction(
            id=tx.id,
            type=tx_type,
            currency=tx.currency,
            amount=Money(*tx.json['amount']),
            status=self._parse_tx_status(tx.state),
            address=data.address if data else None,
            tx_hash=data.tx_hash if data else None,
            fee=Money(*tx.json['fee']),
            info=tx,
            timestamp=created_at.timestamp() if created_at else None,
            datetime=created_at if created_at else None,
        )


class BudaTrading(TradingClient, BudaMarketBase, BudaAuth):
    _wallet_cls = BudaWallet
    min_order_amount_mapping = {
        'BCH': Decimal('0.0001'),
        'BTC': Decimal('0.0001'),
        'ETH': Decimal('0.001'),
        'LTC': Decimal('0.00001'),
    }
    side_mapping = {
        Side.BUY: Buda.OrderType.BID,
        Side.SELL: Buda.OrderType.ASK,
    }
    states_mapping = {
        OrderStatus.OPEN: (Buda.OrderState.PENDING.value, Buda.OrderState.RECEIVED.value),
        OrderStatus.CLOSED: (Buda.OrderState.TRADED.value,),
        OrderStatus.CANCELED: (Buda.OrderState.CANCELED.value, Buda.OrderState.CANCELING.value),
    }

    def _order(self, order_id: str) -> Order:
        order = self.client.order_details(order_id)
        return self._parse_order(order)

    def _open_orders(self, limit: int=None) -> List[Order]:
        @paginated_limit('orders', PER_PAGE)
        def open_orders(page, per_page, state):
            return self.client.order_pages(self.market_id, page, per_page, state)
        orders = []
        for status in self.states_mapping[OrderStatus.OPEN]:
            orders.extend(open_orders(limit, state=status))
        return self._parse_orders_limit(orders, limit)

    def _closed_orders(self, limit: int=None) -> List[Order]:
        @paginated_limit('orders', PER_PAGE)
        def closed_orders(page, per_page, state):
            return self.client.order_pages(self.market_id, page, per_page, state)
        orders = []
        for status in self.states_mapping[OrderStatus.CLOSED]:
            orders.extend(closed_orders(limit, state=status))
        return self._parse_orders_limit(orders, limit)

    def _closed_orders_since(self, since: int) -> List[Order]:
        @paginated_since('orders', PER_PAGE)
        def closed_orders(page, per_page, state):
            return self.client.order_pages(self.market_id, page, per_page, state)
        orders = []
        for status in self.states_mapping[OrderStatus.CLOSED]:
            orders.extend(closed_orders(since, state=status))
        return self._parse_orders_since(orders, since)

    def _cancel_order(self, order_id: str) -> None:
        self.client.cancel_order(order_id)

    def _cancel_orders(self, order_ids: List[str]=None) -> None:
        raise NotSupported

    def _place_order(self, side: Side, o_type: OrderType, amount: Decimal, price: Decimal=None) -> Order:
        side = self.side_mapping[side].value
        order = self.client.new_order(self.market_id, side, o_type.value, float(amount), float(price))
        return self._parse_order(order)

    def _parse_order_status(self, state: str) -> Optional[OrderStatus]:
        for status, mappings in self.states_mapping.items():
            if state in mappings:
                return status

    def _parse_order(self, order: Buda.models.Order) -> Order:
        market = Market(*order.market_id.split('-'))
        assert market == self.market
        order_type = OrderType(order.price_type)
        side_mapping = {'Bid': Side.BUY, 'Ask': Side.SELL}
        side = side_mapping[order.type]
        status = self._parse_order_status(order.state)
        original_amount = Money(*order.json['original_amount'])
        amount = Money(*order.json['amount'])
        traded_amount = Money(*order.json['traded_amount'])
        paid_fee = Money(*order.json['paid_fee'])
        price = Money(*order.json['limit']) if order.price_type == 'limit' else None
        total_exchanged = Money(*order.json['total_exchanged'])
        if total_exchanged and amount:
            price = total_exchanged / traded_amount.amount
        return Order(
            id=order.id,
            market=market,
            type=order_type,
            side=side,
            status=status,
            amount=original_amount,
            remaining=amount,
            filled=traded_amount,
            cost=total_exchanged,
            fee=paid_fee,
            price=price,
            info=order,
            timestamp=order.created_at.timestamp(),
            datetime=order.created_at,
        )
