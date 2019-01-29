from trading_bots.bots import Bot
from trading_bots.contrib.models import Side, Money
from trading_bots.contrib.exchanges import bitstamp, buda
from trading_bots.utils import truncate_to, get_iso_time_str, truncate_money
import pandas as pd
import talib
import time
from operator import itemgetter
import maya


class TechnicalAnalysis(Bot):
    label = 'TechnicalAnalysis'
    market_clients = [
        bitstamp.BitstampMarket,
    ]

    def _setup(self, config):
        # Set buda trading client
        client_params = dict(timeout=self.timeout)
        self.buda = buda.BudaTrading(config['market'], client_params, self.dry_run, self.log, self.store)
        self.store_keys = ('trades', self.buda.market.code.lower())
        # Set reference market client
        self.candle_interval = config['reference']['candle_interval']
        self.reference = self._get_market_client(config['reference']['name'], config['reference']['market'])
        assert self.reference.market.base == self.buda.market.base
        # Init variables
        self.max_base = Money(config['amounts']['max_base'], self.buda.market.base)
        self.max_quote = Money(config['amounts']['max_quote'], self.buda.market.quote)
        self.position = self.store.get('position') or dict(status='closed')
        # Set talib configs
        self.bbands_periods = config['talib']['bbands']['periods']
        self.rsi_periods = config['talib']['rsi']['periods']
        self.rsi_overbought = config['talib']['rsi']['overbought']
        self.rsi_oversold = config['talib']['rsi']['oversold']

    def _algorithm(self):
        # Update candle data and TA indicators
        self.log.info(f'Getting trades from {self.reference.name} {self.reference.market.code}')
        from_time = maya.when('1 day ago').epoch
        trades = self.get_trades(from_time)
        # Create pandas DataFrame from trades and set date as index
        df = pd.DataFrame(trades)
        df.index = df.timestamp.apply(lambda x: pd.datetime.utcfromtimestamp(x))
        # Build 5min candles from trades DataFrame [open, high, close, low]
        df = df.rate.resample(self.candle_interval).ohlc()
        # Calculate Bollinger Bands and RSI from talib
        df['bb_lower'], df['bb_middle'], df['bb_upper'] = talib.BBANDS(df.close, timeperiod=self.bbands_periods)
        df['rsi'] = talib.RSI(df.close, timeperiod=self.rsi_periods)
        lower = self.truncate_price(df.bb_lower[-1])
        middle = self.truncate_price(df.bb_middle[-1])
        upper = self.truncate_price(df.bb_upper[-1])
        self.log.info(f'BB_lower: {lower} | BB_middle: {middle} | BB_upper: {upper}')
        self.log.info(f'RSI: {df.rsi[-1]:.2f}')
        # Check if our position is open or closed
        if self.position['status'] == 'closed':
            # Try conditions to open position
            self.log.info(f'Position is closed, checking to open')
            if df.close[-1] < df.bb_lower[-1] and df.rsi[-1] < self.rsi_oversold:
                # Last price is lower than the lower BBand and RSI is oversold, BUY!
                self.log.info(f'Market oversold! BUY!')
                amount = self.get_amount(Side.BUY)
                if amount >= self.buda.min_order_amount:
                    tx = self.buda.place_market_order(Side.BUY, amount)
                    self.position = {
                        'status': 'open',
                        'side': Side.BUY.value,
                        'amount': repr(tx.amount)
                    }
                else:
                    self.log.warning(f'Available amount is lower than minimum order amount')
            elif df.close[-1] > df.bb_upper[-1] and df.rsi[-1] > self.rsi_overbought:
                # Last price is higher than the upper BBand and RSI is overbought, SELL!
                self.log.info(f'Market overbought! SELL!')
                amount = self.get_amount(Side.SELL)
                if amount >= self.buda.min_order_amount:
                    tx = self.buda.place_market_order(Side.SELL, amount)
                    self.position = {
                        'status': 'open',
                        'side': Side.SELL.value,
                        'amount': repr(tx.amount)
                    }
                else:
                    self.log.warning(f'Available amount is lower than minimum order amount')
            else:
                self.log.info(f'Market conditions unmet to open position')
        else:
            self.log.info(f'Position is open, checking to close')
            if self.position['side'] == Side.BUY.value and df.rsi[-1] >= 30:
                # RSI is back to normal, close Buy position
                self.log.info(f'Market is back to normal, closing position')
                amount = Money.loads(self.position['amount'])
                if amount >= self.buda.min_order_amount:
                    tx = self.buda.place_market_order(Side.SELL, amount)
                    remaining = amount - tx.amount
                    if remaining < self.buda.min_order_amount:
                        self.position = {'status': 'closed'}
                    else:
                        self.position['amount'] = remaining
                else:
                    self.log.warning(f'Available amount is lower than minimum order amount')
            elif self.position['side'] == Side.SELL.value and df.rsi[-1] <= 70:
                # RSI is back to normal, close Sell position
                self.log.info(f'Market is back to normal, closing position')
                amount = Money.loads(self.position['amount'])
                if amount >= self.buda.min_order_amount:
                    tx = self.buda.place_market_order(Side.BUY, amount)
                    remaining = amount - tx.amount
                    if remaining < self.buda.min_order_amount:
                        self.position = {'status': 'closed'}
                    else:
                        self.position['amount'] = repr(remaining)
                else:
                    self.log.warning(f'Available amount is lower than minimum order amount')
            else:
                self.log.info(f'Market conditions unmet to close position')
        self.store.set('position', self.position)

    def _abort(self):
        pass

    def get_amount(self, side):
        if side == Side.BUY:
            available_quote = self.buda.wallets.quote.fetch_balance().free
            amount_quote = min(self.max_quote, available_quote)
            amount_buy = truncate_money(self.buda.fetch_order_book().quote(side, amount_quote).base_amount)
            return amount_buy
        elif side == Side.SELL:
            available_base = self.buda.wallets.base.fetch_balance().free
            amount_base = min(self.max_base, available_base)
            amount_sell = truncate_money(amount_base)
            return amount_sell

    def get_trades(self, from_timestamp: float):
        # Getting previous trades from store
        self.log.debug(f'Fetching trades since %s', get_iso_time_str(from_timestamp))
        prev_trades = self._get_previous_trades() or []
        # Check trades to establish timestamp
        if prev_trades:
            first_trade = prev_trades[0]['timestamp']
            last_trade = prev_trades[-1]['timestamp']
            self.log.debug(f'{len(prev_trades)} previous trades: (%s ... %s)',
                           get_iso_time_str(first_trade), get_iso_time_str(last_trade))
            # Check first_trade < last_trade on file
            assert first_trade < last_trade, f"File's first_trade > last_trade!)"
            # Use file's last trade timestamp whenever possible
            if first_trade < from_timestamp < last_trade:
                query_timestamp = last_trade
            else:
                query_timestamp = from_timestamp
                prev_trades = []
        else:
            self.log.info(f'No trades in store!')
            query_timestamp = from_timestamp
        # Add a null entry with n_days_timestamp (entries are bases on trades IDs)
        trades = [trade for trade in prev_trades if trade.get('timestamp') >= from_timestamp]
        trades.append(dict(timestamp=from_timestamp, rate=0.0, amount=0.0))
        # Poll trades from client
        trades_n = 1000
        n_calls = 0
        while trades_n == 1000:
            self.log.debug(f'Fetching {self.reference.name} trades since: %s',
                           get_iso_time_str(query_timestamp))
            if n_calls > 1:
                time.sleep(1)
            try:
                last_trades, query_timestamp = self._get_trades_call(query_timestamp)
            except Exception:
                self.log.exception(f'Failed obtaining {self.reference.name} trades!')
                raise
            n_calls += 1
            if last_trades:
                self.log.debug(f'Trades found: {len(last_trades)} (%s ... %s)',
                               get_iso_time_str(last_trades[0]['timestamp']),
                               get_iso_time_str(last_trades[-1]['timestamp']))
                trades.extend(last_trades)
            else:
                self.log.debug('No trades found')
            # Sort entries based on timestamp
            trades.sort(key=itemgetter('timestamp'))
            # last trades count
            trades_n = len(last_trades)
            # Store trades
            self.log.debug(f'Storing {len(trades)} trades')
            self._store_trades(trades)
        return trades[1:]

    def reset_trades(self):
        self.store.hdel(*self.store_keys)

    def _get_trades_call(self, query_timestamp: float):
        one_day_seconds = 86400
        time_interval = 'day' if time.time() - query_timestamp >= one_day_seconds else 'hour'
        trades = self.reference.client.transactions(self.reference.market_id, time_interval)
        trades = [
            dict(timestamp=float(trade['date']),
                 rate=float(trade['price']),
                 amount=float(trade['amount']) * (1 if trade['type'] == '0' else -1))  # '0': buy, '1': sell
            for trade in trades
            if float(trade['date']) > query_timestamp]
        trades.sort(key=itemgetter('timestamp'))
        last_timestamp = trades[-1]['timestamp'] + 1 if trades else query_timestamp
        return trades, last_timestamp

    def _get_previous_trades(self):
        return self.store.hget(*self.store_keys, serializer='json')

    def _store_trades(self, trades: list):
        self.store.hset(*self.store_keys, value=trades, serializer='json')

    def _get_market_client(self, name, market):
        for client in self.market_clients:
            if client.name == name:
                print(client.name)
                return client(
                    market, client=None, dry_run=self.dry_run, timeout=self.timeout, logger=self.log,
                    store=self.store)
        raise NotImplementedError(f'Client {name} not found!')

    def truncate_amount(self, value):
        return truncate_to(value, self.buda.market.base)

    def truncate_price(self, value):
        return truncate_to(value, self.buda.market.quote)
