from decimal import Decimal

from trading_bots.bots import Bot
from trading_bots.contrib.exchanges.buda.clients import BudaTrading
from trading_bots.contrib.models import Money, Side
from trading_bots.utils import truncate_money


class RelativeOrders(Bot):
    label = "RelativeOrders"

    def _setup(self, config):
        # Set buda trading client
        client_params = dict(timeout=self.timeout)
        self.buda = BudaTrading(
            config["market"], client_params, self.dry_run, self.log, self.store
        )
        # Set price multipliers
        self.buy_multiplier = Decimal(str(config["prices"]["buy_multiplier"]))
        self.sell_multiplier = Decimal(str(config["prices"]["sell_multiplier"]))
        self.max_base = Money(config["amounts"]["max_base"], self.buda.market.base)
        self.max_quote = Money(config["amounts"]["max_quote"], self.buda.market.quote)

    def _algorithm(self):
        # PREPARE ORDER PRICES
        # Get middle price
        ticker = self.buda.fetch_ticker()
        self.log.info(
            f"Ticker prices   | Bid: {ticker.bid} | Ask: {ticker.ask} | Mid: {ticker.mid}"
        )
        # Offset prices from middle using configured price multipliers
        price_buy = truncate_money(ticker.mid * self.buy_multiplier)
        price_sell = truncate_money(ticker.mid * self.sell_multiplier)
        self.log.info(f"Relative prices | Buy: {price_buy} | Sell: {price_sell}")
        # PREPARE ORDER AMOUNTS
        # Cancel open orders to get correct available amounts
        self.log.info("Closing open orders")
        self.buda.cancel_all_orders()
        # Fetch available balances
        available_base = self.buda.wallets.base.fetch_balance().free
        available_quote = self.buda.wallets.quote.fetch_balance().free
        # Adjust amounts to max in config
        amount_base = min(self.max_base, available_base)
        amount_quote = min(self.max_quote, available_quote)
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
            self.log.critical("Failed!, some orders might not be cancelled")
            raise
        else:
            self.log.info("All open orders were cancelled")
