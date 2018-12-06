from abc import ABC
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

import maya
from cached_property import cached_property
from trading_api_wrappers import Bitstamp

from trading_bots.utils import truncate
from ...clients import *
from ...errors import *
from ...models import *

__all__ = [
    'BitstampPublic',
    'BitstampAuth',
    'BitstampMarket',
    'BitstampWallet',
    'BitstampTrading',
]

side_mapping = {'0': Side.BUY, '1': Side.SELL}


class BitstampBase(BaseClient, ABC):
    name = 'Bitstamp'

    def _markets(self) -> Set[Market]:
        pairs = self.client.trading_pairs_info()
        return {Market(*pair['name'].split('/')) for pair in pairs}


class BitstampPublic(BitstampBase):

    @cached_property
    def client(self) -> Bitstamp.Public:
        return Bitstamp.Public(**self.client_params)


class BitstampAuth(BitstampBase):

    @cached_property
    def client(self) -> Bitstamp.Auth:
        self.check_credentials()
        return Bitstamp.Auth(**self.credentials, **self.client_params)


class BitstampMarketBase(MarketClient, ABC):

    def _market_id(self) -> str:
        return self.market.code.lower()

    def _ticker(self) -> Ticker:
        ticker = self.client.ticker(self.market_id)
        maya_dt = maya.MayaDT(int(ticker['timestamp']))
        currency = self.market.quote
        last = Money(ticker['last'], currency)
        return Ticker(
            market=self.market,
            bid=Money(ticker['bid'], currency),
            ask=Money(ticker['ask'], currency),
            last=last,
            open=Money(ticker['open'], currency),
            high=Money(ticker['high'], currency),
            low=Money(ticker['low'], currency),
            close=last,
            change=None,
            percentage=None,
            average=None,
            vwap=Money(ticker['vwap'], currency),
            info=ticker,
            timestamp=maya_dt.epoch,
            datetime=maya_dt.datetime(),
        )

    def _order_book(self) -> OrderBook:
        order_book = self.client.order_book(self.market_id)
        return self._parse_order_book(order_book)

    def _trades_since(self, since: int) -> List[Trade]:
        one_day_ago = maya.when('1 day ago').epoch
        if since < one_day_ago:
            self.log.warning('Bitstamp only returns 1 day of trades max')
        time_interval = 'day'
        trades = self.client.transactions(self.market_id, time_interval)
        return self._parse_trades(trades, since)

    def _parse_trade(self, trade: Dict) -> Trade:
        trade_id = trade.get('id', trade.get('tid'))
        maya_dt = None
        if 'date' in trade:
            maya_dt = maya.MayaDT(int(trade['date']))
        elif 'datetime' in trade:
            maya_dt = maya.when(trade['datetime'])
        side = trade.get('type')
        if side:
            side = side_mapping[side]
        price = trade.get('price', trade.get(self.market.base.lower()))
        if price:
            price = Money(price, self.market.quote)
        amount = trade.get('amount', trade.get(self.market.code.lower()))
        if amount:
            amount = Money(amount, self.market.base)
        fee = trade.get('fee')
        if fee:
            fee = Money(fee, self.market.quote)
        cost = None
        if price and amount:
            cost = price * amount.amount
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


class BitstampMarket(BitstampMarketBase, BitstampPublic):
    pass


class BitstampWallet(WalletClient, BitstampAuth):
    status_mapping = {
        TxStatus.OK: (2,),
        TxStatus.PENDING: (0, 1),
        TxStatus.FAILED: (4,),
        TxStatus.CANCELED: (3,),
    }

    def _currency_id(self) -> str:
        return self.currency.lower()

    def _balance(self) -> Balance:
        balances = self.client.account_balance()

        def parse_balance(value: str):
            key = f'{self.currency_id}_{value}'
            if key in balances:
                return Money(balances[key], self.currency)

        return Balance(
            total=parse_balance('balance'),
            free=parse_balance('available'),
            used=parse_balance('reserved'),
            info=balances,
        )

    def _deposits(self, *args, **kwargs):
        raise NotImplementedError('Bitstamp does not have an endpoint for past deposits')

    _deposits_since = _deposits

    def _withdrawals_since(self, since: int=None) -> List[Withdrawal]:
        now = maya.now().epoch
        max_delta = 50000000  # 50000000 (seconds)
        min_datetime = maya.MayaDT(now - max_delta)
        min_datetime_msg = f"Bitstamp can't return withdrawals before {min_datetime.rfc2822()}"
        self.log.warning(min_datetime_msg)
        if since is None:
            since = now - max_delta
        time_delta = now - since
        if time_delta > max_delta:
            raise NotSupported(min_datetime_msg)
        withdrawals = self.client.withdrawal_requests(time_delta)
        return self._parse_transactions_since(
            [w for w in withdrawals if w['currency'] == self.currency],
            TxType.WITHDRAWAL, since)

    def _withdrawals(self, limit: int=None) -> List[Withdrawal]:
        withdrawals = self._withdrawals_since()
        return self._filter_limit(withdrawals, limit)

    def _withdraw(self, amount: Decimal, address: str, subtract_fee: bool=False, **params) -> Withdrawal:
        withdrawal_method = {
            'BCH': self.client.bch_withdrawal,
            'BTC': self.client.bitcoin_withdrawal,
            'ETH': self.client.eth_withdrawal,
            'LTC': self.client.litecoin_withdrawal,
            'XRP': self.client.xrp_withdrawal,
        }

        if subtract_fee:
            self.log.warning('subtract_fee option is not supported!')

        method = withdrawal_method[self.currency]
        withdrawal = method(address, amount, **params)

        return self._parse_transaction(withdrawal, TxType.WITHDRAWAL)

    def _parse_withdrawal_status(self, status: str) -> Optional[TxStatus]:
        for _status, mappings in self.status_mapping.items():
            if status in mappings:
                return _status

    def _parse_withdrawal(self, withdrawal: Dict) -> Withdrawal:
        currency = withdrawal.get('currency', self.currency).upper()
        maya_dt = maya.when(withdrawal['datetime']) if 'datetime' in withdrawal else maya.now()
        return Transaction(
            id=withdrawal['id'],
            type=TxType.WITHDRAWAL,
            currency=currency,
            amount=Money(withdrawal['amount'], currency),
            status=self._parse_withdrawal_status(withdrawal['status']),
            address=withdrawal.get('address'),
            tx_hash=withdrawal.get('transaction_id'),
            fee=None,
            info=withdrawal,
            timestamp=maya_dt.epoch,
            datetime=maya_dt.datetime(),
        )

    def _parse_transaction(self, tx: Any, tx_type: TxType) -> Transaction:
        if tx_type == TxType.DEPOSIT:
            raise NotSupported('Bitstamp does not have an endpoint for past deposits')
        return self._parse_withdrawal(tx)


class BitstampTrading(TradingClient, BitstampMarketBase, BitstampAuth):
    _wallet_cls = BitstampWallet
    # Bitstamp lists min_order size on quote currency https://www.bitstamp.net/api/v2/trading-pairs-info/
    min_order_amount_mapping = {
        'BCH': Decimal('0.02'),  # ~ 10.00 USD @ 500.00 BTC/USD
        'BTC': Decimal('0.002'),  # ~ 10.00 USD @ 5000.00 BTC/USD
        'ETH': Decimal('0.05'),  # ~ 10.00 USD @ 200.00 ETH/USD
        'LTC': Decimal('0.2'),  # ~ 10.00 USD @ 50.00 LTC/USD
    }
    status_mapping = {
        'In Queue': OrderStatus.OPEN,
        'Open': OrderStatus.OPEN,
        'Finished': OrderStatus.CLOSED,
    }

    def _order(self, order_id: str) -> Order:
        order = self.client.orders_status(order_id)
        return self._parse_order(order)

    def _open_orders(self, limit: int=None) -> List[Order]:
        orders = self.client.open_orders(self.market_id)
        return self._parse_orders_limit(orders, limit)

    def _closed_orders(self, limit: int=None) -> List[Order]:
        raise NotSupported('Bitstamp only has an endpoint for open orders')

    def _closed_orders_since(self, since: int) -> List[Order]:
        raise NotSupported('Bitstamp only has an endpoint for open orders')

    def _cancel_order(self, order_id: str) -> None:
        return self.client.cancel_order(order_id)

    def _cancel_orders(self, order_ids: List[str]=None) -> None:
        # Bitstamp has 'cancel_all_orders' endpoint but cancels orders on all markets
        raise NotSupported

    def _place_order(self, side: Side, o_type: OrderType, amount: Decimal, price: Decimal=None) -> Order:
        methods = {
            OrderType.MARKET: {
                Side.BUY: self.client.buy_market_order,
                Side.SELL: self.client.sell_market_order,
            },
            OrderType.LIMIT: {
                Side.BUY: self.client.buy_limit_order,
                Side.SELL: self.client.sell_limit_order,
            }
        }
        place_order = methods[o_type][side]
        amount = truncate(amount, 8)
        args = (float(amount), float(price)) if o_type == OrderType.LIMIT else (amount,)
        order = place_order(self.market_id, *args)
        return self._parse_order(order, o_type)

    def _parse_order_status(self, status: str) -> Optional[OrderStatus]:
        return self.status_mapping.get(status)

    def _parse_order(self, order: Dict, order_type: OrderType=None):
        order_id = order.get('id')
        datetime_str = order.get('datetime')
        if datetime_str:
            maya_dt = maya.when(datetime_str)
            timestamp = maya_dt.epoch
            datetime = maya_dt.datetime()
        else:
            timestamp = None
            datetime = None
        market = Market.from_code(order['currency_pair'].upper())
        assert market == self.market
        side = order.get('type')
        if side is not None:
            side = side_mapping[side]
        amount = order.get('amount')
        filled = None
        fee = None
        cost = None
        transactions = order.get('transactions')
        if transactions and isinstance(transactions, list):
            fee = Money(0, self.market.quote)
            filled = Money(0, self.market.base)
            for trade in transactions:
                trade = self._parse_trade(trade)
                filled += trade.amount
                fee += trade.fee
                if cost is None:
                    cost = 0
                cost += trade.cost
        status = self._parse_order_status(order.get('status'))
        if status == 'Finished' and amount is None:
            amount = filled
        remaining = None
        if amount is not None and filled is not None:
            remaining = amount - filled
        price = order.get('price')
        if cost is None and price:
            cost = price * filled.amount
        elif price is None and filled:
            price = cost / filled.amount
        return Order(
            id=order_id,
            market=market,
            type=order_type,
            side=side,
            status=status,
            amount=amount,
            remaining=remaining,
            filled=filled,
            cost=cost,
            fee=fee,
            price=price,
            info=order,
            timestamp=timestamp,
            datetime=datetime,
        )
