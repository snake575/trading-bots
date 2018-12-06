from abc import ABC
from decimal import Decimal
from typing import Any, Dict, List, Set

import maya
from cached_property import cached_property
from trading_api_wrappers import Kraken

from ...clients import *
from ...errors import *
from ...models import *

__all__ = [
    'KrakenPublic',
    'KrakenAuth',
    'KrakenMarket',
    'KrakenWallet',
    'KrakenTrading',
]


class KrakenBase(BaseClient, ABC):
    name: str = 'Kraken'

    def _markets(self) -> Set[Market]:
        # NOTE: Doesn't support Kraken dark pool markets
        pairs = self.client.asset_pairs()['result']

        def generate_markets():
            for key, pair in pairs.items():
                base = pair['base']
                quote = pair['quote']
                if (base[0] == 'X') or (base[0] == 'Z'):
                    base = base[1:]
                if (quote[0] == 'X') or (quote[0] == 'Z'):
                    quote = quote[1:]
                base = self._parse_common_currency(base)
                quote = self._parse_common_currency(quote)
                dark_pool = '.d' in key
                if not dark_pool:
                    yield Market(base, quote)

        return set(generate_markets())

    def _currencies(self) -> Set[str]:
        assets = self.client.assets()['result']

        def generate_assets():
            for key, asset in assets.items():
                yield self._parse_common_currency(asset['altname'])

        return set(generate_assets())


class KrakenPublic(KrakenBase):

    @cached_property
    def client(self) -> Kraken.Public:
        return Kraken.Public(**self.client_params)


class KrakenAuth(KrakenBase):

    @cached_property
    def client(self) -> Kraken.Auth:
        self.check_credentials()
        return Kraken.Auth(**self.credentials, **self.client_params)


class KrakenMarketBase(MarketClient, ABC):

    def _market_id(self) -> str:
        return str(self.market).replace('BTC', 'XBT')

    def _ticker(self) -> Ticker:
        result = self.client.ticker(symbol=self.market_id)['result']
        # Get result first key
        ticker = result[next(iter(result))]
        return self._parse_ticker(ticker)

    def _parse_ticker(self, ticker: Dict) -> Ticker:
        currency = self.market.quote
        last = Money(ticker['c'][0], currency)
        _open = ticker.get('o')
        if _open:
            _open = Money(_open, currency)
        return Ticker(
            market=self.market,
            bid=Money(ticker['b'][0], currency),
            ask=Money(ticker['a'][0], currency),
            last=last,
            open=_open,
            high=Money(ticker['h'][1], currency),
            low=Money(ticker['l'][1], currency),
            close=last,
            change=None,
            percentage=None,
            average=None,
            vwap=Money(ticker['p'][1], currency),
            info=ticker,
        )

    def _order_book(self, side: Side=None):
        result = self.client.order_book(symbol=self.market_id)['result']
        # Get result first key
        order_book = result[next(iter(result))]
        return self._parse_order_book(order_book)

    def _trades_since(self, since: int) -> List[Trade]:
        # TODO: Implement trades_since on Kraken
        raise NotImplementedError

    def _parse_trade(self, trade: Any) -> Trade:
        # TODO: Implement parse_trade on Kraken
        raise NotImplementedError


class KrakenMarket(KrakenMarketBase, KrakenPublic):
    pass


class KrakenWallet(WalletClient, KrakenAuth):
    withdrawal_fees = {
        'BCH': 0.0005,
        'BTC': 0.0005,
        'ETH': 0.01,
        'LTC': 0.01,
    }

    def _balance(self) -> Balance:
        self.log.warning('Kraken only returns total balance')
        asset = self.currency.replace('BTC', 'XXBT').replace('ETH', 'XETH').replace('XLM', 'XXLM').replace('USD', 'ZUSD')
        balance = self.client.balance()
        return Balance(
            total=balance['result'][asset],
            free=None,
            used=None,
        )

    def _deposits(self, limit: int=None) -> List[Deposit]:
        mapping = {
            'BCH': ('BCH', 'Bitcoin Cash'),
            'BTC': ('XBT', 'Bitcoin'),
            'ETH': ('XETH', 'Ether (Hex)'),
            'LTC': ('LTC', 'Litecoin'),
        }
        asset, method = mapping[self.currency]
        deposits = self.client.deposit_status(asset, method)['result']
        return self._parse_transactions_limit(deposits, TxType.DEPOSIT, limit)

    def _deposits_since(self, since: int) -> List[Deposit]:
        raise NotSupported(self.log, 'Kraken only returns recent trades')

    def _withdrawals(self, limit: int=None) -> List[Withdrawal]:
        mapping = {
            'BCH': ('BCH', 'Bitcoin Cash'),
            'BTC': ('XBT', 'Bitcoin'),
            'ETH': ('XETH', 'Ether'),
            'LTC': ('LTC', 'Litecoin'),
        }
        asset, method = mapping[self.currency]
        withdrawals = self.client.withdraw_status(asset, method)['result']
        return self._parse_transactions_limit(withdrawals, TxType.WITHDRAWAL, limit)

    def _withdrawals_since(self, since: int) -> List[Withdrawal]:
        raise NotSupported(self.log, 'Kraken only returns recent trades')

    def _withdraw(self, amount: Decimal, address: str, subtract_fee: bool=False, **params) -> Withdrawal:
        asset = self.currency.replace('BTC', 'XBT').replace('ETH', 'XETH')
        withdraw = self.client.withdraw(asset, amount, address, **params)
        return self._parse_transaction(withdraw, TxType.WITHDRAWAL)

    def _parse_transaction(self, tx: Dict, tx_type: TxType) -> Transaction:
        # TODO: Implement Kraken parse_transaction
        return super()._parse_transaction(tx, tx_type)


class KrakenTrading(TradingClient, KrakenMarketBase, KrakenAuth):
    _wallet_cls = KrakenWallet
    has_batch_cancel = False
    min_order_amount_mapping = {
        'BCH': Decimal('0.002'),
        'BTC': Decimal('0.002'),
        'ETH': Decimal('0.02'),
        'LTC': Decimal('0.002'),
    }

    def _order(self, order_id: str) -> Order:
        order = self.client.query_orders([order_id])['result'][order_id]
        return self._parse_order(order)

    def _open_orders(self, limit: int=None) -> List[Order]:
        orders = self.client.open_orders()['result']['open'].values()
        return self._parse_orders_limit(orders, limit)

    def _closed_orders(self, limit: int=None) -> List[Order]:
        # TODO: Iterate results for closed_orders on Kraken
        orders = self.client.closed_orders()['result']['closed'].values()
        return self._parse_orders_limit(orders, limit)

    def _closed_orders_since(self, since: int) -> List[Order]:
        # TODO: Iterate results for closed_orders_since on Kraken
        orders = self.client.closed_orders(start=since)['result']['closed'].values()
        return self._parse_orders_since(orders, since)

    def _cancel_order(self, order_id: str) -> None:
        self.client.cancel_order(order_id)

    def _cancel_orders(self, order_ids: List[str]=None) -> None:
        raise NotSupported

    def _place_order(self, side: Side, order_type: OrderType, amount: Decimal, price: Decimal=None) -> Order:
        order = self.client.add_order(self.market_id, side.value, order_type.value, float(amount), float(price))
        return self._parse_order(order)

    def _parse_order(self, order: Dict) -> Order:
        description = order['descr']
        side = Side(description['type'])
        try:
            order_type = OrderType(description['ordertype'])
        except ValueError:
            order_type = None
        pair: str = description['pair']
        if pair.startswith('USDT'):
            market = Market('USDT', pair[:3])
        else:
            market = Market.from_code(pair)
        maya_dt = maya.MayaDT(float(order['opentm']))
        amount = self.safe_money(order, 'vol', market.base)
        filled = self.safe_money(order, 'vol_exec', market.base)
        remaining = amount - filled
        fee = None
        cost = self.safe_money(order, 'cost', market.quote)
        price = self.safe_money(description, 'price', market.quote)
        if not price:
            price = self.safe_money(description, 'price2', market.quote)
        if not price:
            price = self.safe_money(order, 'price', market.quote)
        if 'fee' in order:
            flags = order['oflags']
            fee_amount = order.get('fee', 0)
            fee_currency = None
            if flags.find('fciq') >= 0:
                fee_currency = market.quote
            elif flags.find('fcib') >= 0:
                fee_currency = market.base
            if fee_currency:
                fee = Money(fee_amount, fee_currency)
        return Order(
            id=order.get('id'),
            market=market,
            type=order_type,
            side=side,
            status=order['status'],
            amount=amount,
            remaining=remaining,
            filled=filled,
            cost=cost,
            fee=fee,
            price=price,
            info=order,
            timestamp=maya_dt.epoch,
            datetime=maya_dt.datetime(),
        )
