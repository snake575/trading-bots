from collections import namedtuple
from decimal import Decimal
from functools import wraps
from operator import attrgetter

import maya
import pytest

from trading_bots.contrib.clients import *
from trading_bots.contrib.errors import *
from trading_bots.contrib.exchanges import *
from trading_bots.contrib.models import *

E = namedtuple('Exchange', 'exchange name market')

EXCHANGES = [
    E(Bitfinex, 'bitfinex', Market('BTC', 'USD')),
    E(Bitstamp, 'bitstamp', Market('BTC', 'USD')),
    E(Buda, 'buda', Market('BTC', 'CLP')),
    E(Kraken, 'kraken', Market('ETH', 'BTC')),
]


def skip_allowed_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except NotSupported:
            pytest.skip('NotSupported')
        except NotImplementedError:
            pytest.skip('NotImplemented')
    return wrapper


# BaseClient ----------------------------------------------------------------

@pytest.fixture(params=EXCHANGES, ids=attrgetter('name'))
def exchange(request) -> Exchange:
    return request.param.exchange()


class TestExchange:

    @skip_allowed_errors
    def test_isinstance(self, exchange):
        assert isinstance(exchange, Exchange)

    @skip_allowed_errors
    def test_markets(self, exchange):
        markets = exchange.markets
        assert markets
        for market in markets:
            assert isinstance(market, Market)


# MarketClient ----------------------------------------------------------------

@pytest.fixture(params=EXCHANGES, ids=attrgetter('name'))
def market_client(request) -> MarketClient:
    return request.param.exchange().Market(request.param.market)


class TestMarketClient:

    @skip_allowed_errors
    def test_isinstance(self, market_client):
        assert isinstance(market_client, MarketClient)

    @skip_allowed_errors
    def test_fetch_ticker(self, market_client):
        ticker = market_client.fetch_ticker()
        assert isinstance(ticker, Ticker)

    @skip_allowed_errors
    def test_fetch_order_book(self, market_client):
        ticker = market_client.fetch_order_book()
        assert isinstance(ticker, OrderBook)

    @skip_allowed_errors
    def test_fetch_trades_since(self, market_client):
        maya_dt = maya.when('1 hour ago')
        trades = market_client.fetch_trades_since(maya_dt.epoch)
        if not trades:
            pytest.skip(f'There are no trades since {maya_dt.rfc2822()}')
        for trade in trades:
            assert isinstance(trade, Trade)


# OrderBook -------------------------------------------------------------------

order_book = OrderBook(
    market=Market.from_code('BTCUSD'),
    asks=[OrderBookEntry(Money(Decimal(1 + i) / 100, 'USD'), Money(1 + i, 'BTC')) for i in range(5)],
    bids=[OrderBookEntry(Money(Decimal(1 + i) / 100, 'USD'), Money(1 + i, 'BTC')) for i in range(5)],
)


@pytest.fixture(params=[Side.BUY, Side.SELL], ids=attrgetter('value'))
def side(request) -> Side:
    return request.param


class TestOrderBook:

    @skip_allowed_errors
    def test_order_book_get_side(self, side):
        order_book_side = order_book.get_book_side(side)
        if not order_book_side:
            pytest.skip(f'Order book ({side}) is empty')
        for entry in order_book_side:
            assert isinstance(entry, OrderBookEntry)

    @skip_allowed_errors
    def test_order_book_quote_average_price(self, side):
        amount = Money(1, order_book.market.base)
        quote = order_book.quote_average_price(side, amount)
        assert isinstance(quote, Money)
        assert order_book.market.quote == quote.currency

    @skip_allowed_errors
    def test_order_book_quote_spread_details(self):
        slippage = Money(1, order_book.market.base)
        spread = order_book.quote_spread_details(slippage)
        assert len(spread) == 3
        for value in spread:
            assert isinstance(value, Money)

    @skip_allowed_errors
    def test_order_book_volume_details(self):
        volume = order_book.volume_details
        assert len(volume) == 3
        for value in volume:
            assert isinstance(value, Money)

    @skip_allowed_errors
    def test_order_book_vw_price(self):
        vw_price = order_book.vw_price
        assert isinstance(vw_price, Money)


# WalletClient ----------------------------------------------------------------

@pytest.fixture(params=EXCHANGES, ids=attrgetter('name'))
def wallet_client(request) -> WalletClient:
    return request.param.exchange().Wallet(request.param.market.quote)


parametrize_tx_type = pytest.mark.parametrize('tx_type', ['withdrawals', 'deposits'])


class TestWalletClient:    
    
    @skip_allowed_errors
    def test_wallet_client_instance(self, wallet_client):
        assert isinstance(wallet_client, WalletClient)

    @skip_allowed_errors
    def test_fetch_balance(self, wallet_client):
        balance = wallet_client.fetch_balance()
        assert isinstance(balance, Balance)
    
    @skip_allowed_errors
    def test_fetch_balance_total(self, wallet_client):
        balance = wallet_client.fetch_balance()
        assert balance.total is not None
        if balance.free is None:
            pytest.skip('Free balance is None')
        if balance.used is None:
            pytest.skip('Used balance is None')
        assert balance.free + balance.used == balance.total
    
    @skip_allowed_errors
    @parametrize_tx_type
    def test_fetch_transactions(self, wallet_client, tx_type):
        limit = 1
        method = getattr(wallet_client, f'fetch_{tx_type}')
        transactions = method(limit)
        assert len(transactions) <= limit
        if len(transactions) < limit:
            pytest.skip(f'Not enough transactions (required={limit})')
        for transaction in transactions:
            assert isinstance(transaction, Transaction)
    
    @skip_allowed_errors
    @parametrize_tx_type
    def test_fetch_transactions_since(self, wallet_client, tx_type):
        method = getattr(wallet_client, f'fetch_{tx_type}_since')
        maya_dt = maya.when('3 months ago')
        transactions = method(maya_dt.epoch)
        if not transactions:
            pytest.skip(f'There are no transactions since {maya_dt.rfc2822()}')
        for transaction in transactions:
            assert isinstance(transaction, Transaction)


# TradingClient ---------------------------------------------------------------

@pytest.fixture(params=EXCHANGES, ids=attrgetter('name'))
def trading_client(request) -> TradingClient:
    return request.param.exchange().Trading(request.param.market)


class TestTradingClient:

    @skip_allowed_errors
    def test_trading_client_instance(self, trading_client):
        assert isinstance(trading_client, TradingClient)
    
    @skip_allowed_errors
    def test_trading_client_instance_wallets(self, trading_client):
        wallets = trading_client.wallets
        assert isinstance(wallets.base, WalletClient)
        assert isinstance(wallets.quote, WalletClient)
    
    @skip_allowed_errors
    def test_fetch_open_orders(self, trading_client):
        limit = 1
        orders = trading_client.fetch_open_orders(limit)
        assert len(orders) <= limit
        if len(orders) < limit:
            pytest.skip(f'Not enough orders (required={limit})')
        for order in orders:
            assert isinstance(order, Order)
    
    @skip_allowed_errors
    def test_fetch_closed_orders(self, trading_client):
        limit = 1
        orders = trading_client.fetch_closed_orders(limit)
        assert len(orders) <= limit
        if len(orders) < limit:
            pytest.skip(f'Not enough orders (required={limit})')
        for order in orders:
            assert isinstance(order, Order)
    
    @skip_allowed_errors
    def test_fetch_closed_orders_since(self, trading_client):
        from trading_bots.contrib.exchanges.bitfinex.clients import BitfinexTrading
        maya_dt = maya.when('3 months ago')
        if isinstance(trading_client, BitfinexTrading):
            maya_dt = maya.when('1 day ago')
        orders = trading_client.fetch_closed_orders_since(maya_dt.epoch)
        if not orders:
            pytest.skip(f'There are no orders since {maya_dt.rfc2822()}')
        for order in orders:
            assert isinstance(order, Order)

    @skip_allowed_errors
    def test_fetch_order(self, trading_client):
        limit = 1
        orders = trading_client.fetch_closed_orders(limit)
        assert len(orders) <= limit
        if not orders:
            pytest.skip(f'Not enough orders (required={limit})')
        test_order = orders[0]
        if not test_order.id:
            pytest.skip(f'Test order has no ID')
        order = trading_client.fetch_order(test_order.id)
        assert isinstance(order, Order)
        assert order == test_order
