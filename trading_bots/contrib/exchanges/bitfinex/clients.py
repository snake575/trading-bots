from abc import ABC
from decimal import Decimal
from logging import Logger
from typing import Dict, List, Set

import maya
from cached_property import cached_property
from trading_api_wrappers import Bitfinex
from trading_api_wrappers import BitfinexV2

from trading_bots.core.storage import Store
from ...clients import *
from ...errors import *
from ...models import *

__all__ = [
    'BitfinexPublic',
    'BitfinexAuth',
    'BitfinexMarket',
    'BitfinexWallet',
    'BitfinexTrading',
]

DEFAULT_WALLET_TYPE = 'exchange'


class BitfinexBase(BaseClient, ABC):
    name: str = 'Bitfinex'

    def _markets(self) -> Set[Market]:
        symbols = self.client.symbols()
        return {Market.from_code(symbol.upper()) for symbol in symbols}


class BitfinexPublic(BitfinexBase):

    @cached_property
    def client_v1(self) -> Bitfinex.Public:
        return Bitfinex.Public(**self.client_params)

    @cached_property
    def client_v2(self) -> BitfinexV2.Public:
        return BitfinexV2.Public(**self.credentials, **self.client_params)

    @cached_property
    def client(self) -> Bitfinex.Public:
        return self.client_v1


class BitfinexAuth(BitfinexBase):

    @cached_property
    def client(self) -> Bitfinex.Auth:
        return Bitfinex.Auth(**self.client_params)


class BitfinexMarketBase(MarketClient, ABC):

    @cached_property
    def market_id_v2(self) -> str:
        return 't' + self.market_id

    def _ticker(self) -> Ticker:
        ticker = self.client.ticker(symbol=self.market_id)
        return self._parse_ticker(ticker)

    def _parse_ticker(self, ticker: Dict) -> Ticker:
        currency = self.market.quote
        maya_dt = maya.MayaDT(float(ticker['timestamp']))
        last = self.safe_money(ticker, 'last_price', currency)
        return Ticker(
            market=self.market,
            bid=self.safe_money(ticker, 'bid', currency),
            ask=self.safe_money(ticker, 'ask', currency),
            last=last,
            open=None,
            high=self.safe_money(ticker, 'high', currency),
            low=self.safe_money(ticker, 'low', currency),
            close=last,
            change=None,
            percentage=None,
            average=self.safe_money(ticker, 'mid', currency),
            vwap=None,
            info=ticker,
            timestamp=maya_dt.epoch,
            datetime=maya_dt.datetime(),
        )

    def _order_book(self, side: Side=None) -> OrderBook:
        # Max limit is 5000 per side
        order_book = self.client.order_book(symbol=self.market_id, limit_asks=1000, limit_bids=1000)
        return self._parse_order_book(order_book)

    def _parse_order_book_entry(self, order: Dict) -> OrderBookEntry:
        return OrderBookEntry(
            price=Money(order['price'], self.market.quote),
            amount=Money(order['amount'], self.market.base),
        )

    def _trades_since(self, since: int) -> List[Trade]:

        def fetch_trades():
            data = {}
            timestamp = since * 1000  # in ms
            max_limit = 1000
            while True:
                entries = self.client_v2.trades(self.market_id_v2, start=timestamp, limit=max_limit, sort=True)
                data.update({entry.ID: entry for entry in entries})
                if len(entries) < max_limit:
                    return data
                timestamp = entries[-1].MTS

        trades = fetch_trades()
        return self._parse_trades(list(trades.values()), since)

    def _parse_trade(self, trade: BitfinexV2.models.TradingTrade) -> Trade:
        trade_id = str(trade.ID)
        maya_dt = maya.MayaDT(trade.MTS / 1000)
        amount = abs(Money(str(trade.AMOUNT), self.market.base))
        price = Money(str(trade.PRICE), self.market.quote)
        side = Side.BUY if trade.AMOUNT > 0 else Side.SELL
        cost = price * amount.amount
        fee = None
        return Trade(
            id=trade_id,
            market=self.market,
            type=None,
            side=side,
            amount=amount,
            price=price,
            cost=cost,
            fee=fee,
            info=trade,
            timestamp=maya_dt.epoch,
            datetime=maya_dt.datetime(),
        )


class BitfinexMarket(BitfinexMarketBase, BitfinexPublic):
    pass


class BitfinexWallet(WalletClient, BitfinexAuth):
    withdrawal_fees = {
        'BCH': 0.0005,
        'BTC': 0.0005,
        'ETH': 0.01,
        'LTC': 0.01,
    }
    method_mapping = {
        'BCH': 'bcash',
        'BTC': 'bitcoin',
        'ETH': 'ethereum',
        'LTC': 'litecoin',
    }

    def __init__(self, currency: str, client_params: Dict=None, dry_run: bool=False,
                 logger: Logger=None, store: Store=None, name: str=None,
                 wallet_type: str=DEFAULT_WALLET_TYPE, **kwargs):
        super().__init__(currency, client_params, dry_run, logger, store, name, **kwargs)
        self.wallet_type = wallet_type

    def _balance(self) -> Balance:
        balances = self.client.balances()
        currency = self.currency.lower()
        balance = next(b for b in balances if b['currency'] == currency
                       and b['type'] == self.wallet_type)
        free = Money(balance['available'], self.currency)
        total = Money(balance['amount'], self.currency)
        return Balance(
            total=total,
            free=free,
            used=total - free,
            info=balance,
        )

    def __transactions(self, tx_type: TxType, limit: int=None) -> List[Deposit]:

        def get_transfers():
            data = {}
            timestamp = None
            max_limit = 999
            if limit:
                if limit > max_limit:
                    raise ValueError(f'Cant return more than {max_limit}')
                self.log.warning(f'Bitfinex last {limit} {tx_type.value} for the last {max_limit} transactions')
            while True:
                entries = self.client.movements(self.currency, until=timestamp, limit=max_limit)
                data.update({entry['id']: entry for entry in entries if entry['type'] == tx_type.name})
                if len(entries) < max_limit:
                    return data
                timestamp = entries[-1]['timestamp_created']

        transfers = get_transfers()
        return self._parse_transactions_limit(list(transfers.values()), tx_type, limit)

    def __transactions_since(self, tx_type: TxType, since: int) -> List[Deposit]:

        def get_transfers():
            data = {}
            timestamp = since
            max_limit = 999
            while True:
                entries = self.client.movements(self.currency, since=timestamp, limit=max_limit)
                data.update({entry['id']: entry for entry in entries if entry['type'] == tx_type.name})
                if len(entries) < max_limit:
                    return data
                timestamp = entries[0]['timestamp_created']

        transfers = get_transfers()
        return self._parse_transactions_since(list(transfers.values()), tx_type, since)

    def _deposits(self, limit: int=None) -> List[Deposit]:
        return self.__transactions(TxType.DEPOSIT, limit)

    def _deposits_since(self, since: int) -> List[Deposit]:
        return self.__transactions_since(TxType.DEPOSIT, since)

    def _withdrawals(self, limit: int=None) -> List[Withdrawal]:
        return self.__transactions(TxType.WITHDRAWAL, limit)

    def _withdrawals_since(self, since: int) -> List[Withdrawal]:
        return self.__transactions_since(TxType.WITHDRAWAL, since)

    def _parse_transaction(self, tx: Dict, tx_type: TxType) -> Transaction:
        maya_dt = maya.MayaDT(float(tx['timestamp_created']))
        timestamp = maya_dt.epoch
        datetime = maya_dt.datetime()
        status = tx.get('status')
        if status is not None:
            status_mapping = {
                'CANCELED': TxStatus.CANCELED,
                'ZEROCONFIRMED': TxStatus.FAILED,
                'COMPLETED': TxStatus.OK,
            }
            status = status_mapping.get(status)
        fee = tx.get('fee')
        if fee is not None:
            fee = abs(Money(fee, self.currency))
        return Transaction(
            id=tx.get('id'),
            type=tx_type,
            currency=self.currency,
            amount=Money(tx['amount'], self.currency),
            status=status,
            address=tx.get('address'),
            tx_hash=tx.get('txid'),
            fee=fee,
            timestamp=timestamp,
            datetime=datetime,
            info=tx,
        )

    def _withdraw(self, amount: Number, address: str, subtract_fee: bool=False, **params) -> Withdrawal:
        method = self.method_mapping[self.currency]
        if subtract_fee:
            fee = self.withdrawal_fees[self.currency]
            amount -= fee
        withdrawal = self.client.withdraw(method, 'exchange', amount, address, **params)
        return self._parse_transaction(withdrawal, TxType.WITHDRAWAL)


class BitfinexTrading(TradingClient, BitfinexMarketBase, BitfinexAuth):
    _wallet_cls = BitfinexWallet
    has_batch_cancel = False
    min_order_amount_mapping = {
        'BCH': Decimal('0.02'),
        'BTC': Decimal('0.002'),
        'ETH': Decimal('0.04'),
        'LTC': Decimal('0.02'),
    }
    order_type_mapping = {
        OrderType.MARKET: 'exchange market',
        OrderType.LIMIT: 'exchange limit',
    }

    def _order(self, order_id: str) -> Order:
        order = self.client.status_order(int(order_id))
        return self._parse_order(order)

    def _open_orders(self, limit: int=None) -> List[Order]:
        orders = self.client.active_orders()
        return self._parse_orders_limit(orders, limit)

    def _closed_orders(self, limit: int=None) -> List[Order]:
        self.log.warning('Bitfinex only returns orders for the last 3 days')
        orders = self._parse_orders_limit(self.client.orders_history(limit), limit)
        return [o for o in orders if o.status == OrderStatus.CLOSED]

    def _closed_orders_since(self, since: int) -> List[Order]:
        if since < maya.when('3 days ago').epoch:
            raise ExchangeError('Bitfinex only returns orders for the last 3 days')
        return self._filter_since(self._closed_orders(), since)

    def _cancel_order(self, order_id: str) -> None:
        self.client.delete_order(int(order_id))

    def _cancel_orders(self, order_ids: List[str] = None) -> None:
        # Bitfinex has 'delete_all_orders' endpoint but cancels orders on all markets
        raise NotSupported('Bitfinex has endpoint cancels orders on all markets')

    def _place_order(self, side: Side, o_type: OrderType, amount: Decimal, price: Decimal=None) -> Order:
        order_type = self.order_type_mapping[o_type]
        order = self.client.place_order(float(amount), float(price), side.value, order_type, self.market_id)
        return self._parse_order(order)

    def _parse_order(self, order: Dict) -> Order:
        market = Market.from_code(order['symbol'].upper())
        order_type = order['type']
        assert DEFAULT_WALLET_TYPE in order_type
        order_type = OrderType(order_type.split()[1])
        side = Side(order['side'])
        if order['is_live']:
            status = OrderStatus.OPEN
        elif order['is_cancelled']:
            status = OrderStatus.CANCELED
        else:
            status = OrderStatus.CANCELED
        maya_dt = maya.MayaDT(float(order['timestamp']))
        amount = Money(order['original_amount'], market.base)
        remaining = Money(order['remaining_amount'], market.base)
        filled = Money(order['executed_amount'], market.base)
        price = Money(order['price'], market.quote)
        if filled:
            price = Money(order['avg_execution_price'], market.quote)
        cost = None
        if price:
            cost = price * filled.amount
        return Order(
            id=str(order['id']),
            market=market,
            type=order_type,
            side=side,
            status=status,
            amount=amount,
            remaining=remaining,
            filled=filled,
            cost=cost,
            fee=None,
            price=price,
            info=order,
            timestamp=maya_dt.epoch,
            datetime=maya_dt.datetime(),
        )
