from decimal import Decimal

from trading_bots.bots import Bot
from trading_bots.conf import settings
from trading_bots.contrib.converters.open_exchange_rates import OpenExchangeRates
from trading_bots.contrib.exchanges import bitfinex, bitstamp, buda, kraken
from trading_bots.contrib.models import Money, Side
from trading_bots.utils import truncate_money


class SimpleLimit(Bot):
    label = "SimpleLimit"
    market_clients = [
        buda.BudaMarket,
        bitfinex.BitfinexMarket,
        bitstamp.BitstampMarket,
        kraken.KrakenMarket,
    ]

    def _setup(self, config):
        # Set buda trading client
        client_params = dict(timeout=self.timeout)
        self.buda = buda.BudaTrading(
            config["market"], client_params, self.dry_run, self.log, self.store
        )
        # Set reference market client
        self.reference = self._get_market_client(
            config["reference"]["name"], config["reference"]["market"]
        )
        assert self.reference.market.base == self.buda.market.base
        # Set converter
        app_id = settings.credentials["OpenExchangeRates"]["app_id"]
        self.converter = OpenExchangeRates(
            return_decimal=True, client_params=dict(app_id=app_id)
        )
        # Set price multipliers
        self.buy_multiplier = Decimal(str(config["prices"]["buy_multiplier"]))
        self.sell_multiplier = Decimal(str(config["prices"]["sell_multiplier"]))
        # Set max amounts
        self.max_base = Money(config["amounts"]["max_base"], self.buda.market.base)
        self.max_quote = Money(config["amounts"]["max_quote"], self.buda.market.quote)

    def _algorithm(self):
        # Setup
        self.log.info(
            f"Preparing prices using {self.reference.name} {self.reference.market.code}"
        )
        ref_bid, ref_ask = self._get_reference_prices()
        self.log.info(
            f"Reference prices on {self.reference.name}: Bid: {ref_bid} Ask: {ref_ask}"
        )
        # Set offset prices from reference and price multiplier
        price_buy = truncate_money(ref_bid * self.buy_multiplier)
        price_sell = truncate_money(ref_ask * self.sell_multiplier)
        self.log.info(
            f"{self.buda.market} calculated prices: Buy: {price_buy} Sell: {price_sell}"
        )
        # Cancel open orders
        self.log.info("Closing open orders")
        self.buda.cancel_all_orders()
        # Get available balances
        self.log.info(f"Preparing amounts")
        # Fetch available balances
        available_base = self.buda.wallets.base.fetch_balance().free
        available_quote = self.buda.wallets.quote.fetch_balance().free
        # Adjust amounts to max in config
        amount_base = min(self.max_base, available_base)
        amount_quote = min(self.max_quote, available_quote)
        self.log.info(f"Amounts | Bid: {amount_base} | Ask: {amount_quote}")
        # Get order buy and sell amounts
        # *quote amount must be converted to base
        amount_buy = truncate_money(
            Money(amount_quote / price_buy, self.buda.market.base)
        )
        amount_sell = truncate_money(amount_base)
        self.log.info(f"Amounts | Buy {amount_buy} | Sell {amount_sell}")
        # PLACE ORDERS
        self.log.info("Starting order deployment")
        if amount_buy >= self.buda.min_order_amount:
            self.buda.place_limit_order(
                side=Side.BUY, amount=amount_buy, price=price_buy
            )
        if amount_sell >= self.buda.min_order_amount:
            self.buda.place_limit_order(
                side=Side.SELL, amount=amount_sell, price=price_sell
            )

    def _abort(self):
        self.log.error("Aborting strategy, cancelling all orders")
        try:
            self.buda.cancel_all_orders()
        except Exception:
            self.log.critical(f"Failed!, some orders might not be cancelled")
            raise
        else:
            self.log.info(f"All open orders were cancelled")

    def _get_reference_prices(self):
        ticker = self.reference.fetch_ticker()
        ref_bid, ref_ask = ticker.bid, ticker.ask
        # Convert reference_price if reference market differs from current market
        if self.reference.market != self.buda.market:
            # Get conversion rate (eg CLP/USD from OpenExchangeRates)
            rate = self.converter.get_rate_for(
                self.reference.market.quote, self.buda.market.quote
            )
            self.log.info(
                f"{self.reference.market.quote}/{self.buda.market.quote} rate: {rate:.2f}"
                f" from {self.converter.name}"
            )
            # Get market price according to reference (eg BTC/CLP converted from converter's BTC/USD)
            ref_bid = Money(ref_bid.amount * rate, self.buda.market.quote)
            ref_ask = Money(ref_ask.amount * rate, self.buda.market.quote)
        return ref_bid, ref_ask

    def _get_market_client(self, name, market):
        for client in self.market_clients:
            if client.name == name:
                return client(
                    market,
                    client=None,
                    dry_run=self.dry_run,
                    timeout=self.timeout,
                    logger=self.log,
                    store=self.store,
                )
        raise NotImplementedError(f"Client {name} not found!")
