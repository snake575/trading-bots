# Trading Bots - Simple Limit example

Example use case of Bots framework for creating and running cryptocurrency trading bots.

## Overview

Buying and selling at market price on illiquid markets can be hard on the execution price. Our first reaction would be to use limit orders, nevertheless illiquid markets can take time to fill this orders while price changes constantly and competing traders outbids our orders.

Simple Limit is an easy way to use of buy and sell limit orders. It allows us to auto renew our orders using a reference market and a simple price multiplier to set an offset for our orders.
The reference market should be active enough to take its price as a good reference and place our limit orders at a higher or lower price.


## Installation

Clone or download this repository to your working environment
```bash
$ git clone https://github.com/budacom/buda-bots.git
```

Install dependencies using pipenv (or pip, of course)
```bash
$ pipenv install
```

Then, activate the virtual enviroment:
```bash
$ pipenv shell
```
We are ready!

## Authentication

### API Key

Copy the file `secrets.yml.example` and rename it to `secrets.yml`. Then fill with an API key and secret to access your Buda.com account.

### Warnings

- This library will create live orders at Buda.com cryptocurrency exchange. Please review the code and check all the parameters of your strategy before entering your keys and running the bot.
- This example bot requires a currency converter, by default Open Exchange Rates is needed Register and get you api key for free [here](https://openexchangerates.org/signup/free).


## Usage

For more references, go to the [official documentation](https://github.com/budacom/trading-bots/blob/master/README.md).

### Setup Config File

Found at `example_bots/simple_limit/configs` folder. Its a yaml file that allows us to easily set parameters.

**Example:**
```yml
market: BTCCLP              # Buda.com market where orders will be placed
reference:
  name: Bitstamp            # Reference exchange to use for price
  market: BTCUSD            # Reference market to use for price
prices:
  buy_multiplier: 0.95      # Price multiplier for buy order, ie: 1.05 is 5% above reference
  sell_multiplier: 1.05     # Price multiplier for sell order, ie: 0.95 is 5% under reference
amounts:
 max_base: 1                #  Max amount on sell order, ie: base is BTC on BTCCLP
 max_quote: 2500000        #  Max amount on buy order, ie: quote is CLP on BTCCLP
```

## Bot Strategy



### Setup

```python
def _setup(self, config):
    # Set buda trading client
    client_params = dict(timeout=self.timeout)
    self.buda = buda.BudaTrading(config['market'], client_params, self.dry_run, self.log, self.store)
    # Set reference market client
    self.reference = self._get_market_client(config['reference']['name'], config['reference']['market'])
    assert self.reference.market.base == self.buda.market.base
    # Set converter
    app_id = settings.credentials['OpenExchangeRates']['app_id']
    self.converter = OpenExchangeRates(return_decimal=True, client_params=dict(app_id=app_id))
    # Set price multipliers
    self.buy_multiplier = Decimal(str(config['prices']['buy_multiplier']))
    self.sell_multiplier = Decimal(str(config['prices']['sell_multiplier']))
    # Set max amounts
    self.max_base = Money(config['amounts']['max_base'], self.buda.market.base)
    self.max_quote = Money(config['amounts']['max_quote'], self.buda.market.quote)
```

- Initializes placeholders for our `prices` and `amounts`.
- Also setup our clients and variables according to the reference `market` on our configs.

### Algorithm

We describe our instructions following our desired automation logic:

```python
def _algorithm(self):
    # Setup
    self.log.info(f'Preparing prices using {self.reference.name} {self.reference.market.code}')
    ref_bid, ref_ask = self._get_reference_prices()
    self.log.info(f'Reference prices on {self.reference.name}: Bid: {ref_bid} Ask: {ref_ask}')
    # Set offset prices from reference and price multiplier
    price_buy = truncate_money(ref_bid * self.buy_multiplier)
    price_sell = truncate_money(ref_ask * self.sell_multiplier)
    self.log.info(f'{self.buda.market} calculated prices: Buy: {price_buy} Sell: {price_sell}')
    # Cancel open orders
    self.log.info('Closing open orders')
    self.buda.cancel_all_orders()
    # Get available balances
    self.log.info(f'Preparing amounts')
    # Fetch available balances
    available_base = self.buda.wallets.base.fetch_balance().free
    available_quote = self.buda.wallets.quote.fetch_balance().free
    # Adjust amounts to max in config
    amount_base = min(self.max_base, available_base)
    amount_quote = min(self.max_quote, available_quote)
    self.log.info(f'Amounts | Bid: {amount_base} | Ask: {amount_quote}')
    # Get order buy and sell amounts
    # *quote amount must be converted to base
    amount_buy = truncate_money(Money(amount_quote / price_buy, self.buda.market.base))
    amount_sell = truncate_money(amount_base)
    self.log.info(f'Amounts | Buy {amount_buy} | Sell {amount_sell}')
    # PLACE ORDERS
    self.log.info('Starting order deployment')
    if amount_buy >= self.buda.min_order_amount:
        self.buda.place_limit_order(side=Side.BUY, amount=amount_buy, price=price_buy)
    if amount_sell >= self.buda.min_order_amount:
        self.buda.place_limit_order(side=Side.SELL, amount=amount_sell, price=price_sell)

def _get_reference_prices(self):
    ticker = self.reference.fetch_ticker()
    ref_bid, ref_ask = ticker.bid, ticker.ask
    # Convert reference_price if reference market differs from current market
    if self.reference.market != self.buda.market:
        # Get conversion rate (eg CLP/USD from OpenExchangeRates)
        rate = self.converter.get_rate_for(self.reference.market.quote, self.buda.market.quote)
        self.log.info(f'{self.reference.market.quote}/{self.buda.market.quote} rate: {rate:.2f}'
                      f' from {self.converter.name}')
        # Get market price according to reference (eg BTC/CLP converted from converter's BTC/USD)
        ref_bid = Money(ref_bid.amount * rate, self.buda.market.quote)
        ref_ask = Money(ref_ask.amount * rate, self.buda.market.quote)
    return ref_bid, ref_ask
```


**Prepare prices**
- First, we fetch the price `ticker` from our reference `exchange` and `market`.
- Our reference price gets converted to our market's quote currency and is saved as `ref_bid` and `ref_ask`.
- We offset our reference prices using our `multipliers` from configs and save them as `price_buy` and `price_sell`.

**Prepare order amounts:**
- Cancel all pending orders at the selected market on Buda.com. This frees balance to use on our orders.
- Get available balance amounts from Buda.com's API.
- Validates against max allowed amount from our configs `max_base` and `max_quote`.
- Sets the amounts to be used on orders as `amount_buy` and `amount_sell`.

**Place orders:**
- Checks order amounts against minimum allowed by Buda.com.
- Places our orders at the exchange (You can test with `dry_run: True` flag on global settings to be safe).

### Abort

As important as our strategy is providing abort instructions which is the piece of code that executes in case anything goes wrong:

```python
def _abort(self):
    self.log.error('Aborting strategy, cancelling all orders')
    try:
        self.buda.cancel_all_orders()
    except Exception:
        self.log.critical(f'Failed!, some orders might not be cancelled')
        raise
    else:
        self.log.info(f'All open orders were cancelled')
```
- Basic abort function, we want to cancel all pending orders and exit.

## Running bots

Test by running the desired bot once from console:
```bash
$ python bots.py run SimpleLimit
```

Flag `--config` can be specified to change the default config file:
```bash
$ python bots.py run SimpleLimit --config /path/to/simple-limit_other.yml
```

Now, we need this to run on a loop, we should use `loop` option indicating `--interval` as seconds:
```bash
$ python bots.py loop SimpleLimit --interval 300
```

Running multiple bots for different markets is possible using multiple shells and config files:

Shell 1:
```bash
$ python bots.py loop SimpleLimit --interval 300 --config simple-limit_btcclp.yml
```
Shell 2:
```bash
$ python bots.py loop SimpleLimit --interval 300 --config simple-limit_ethclp.yml
```


## Contributing

Fork this code, BUIDL bots, submit a pull request :muscle:!
