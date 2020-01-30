# Trading Bots - Any to Any example

Example use case of Bots framework for creating and running cryptocurrency trading bots.

## Overview

Trading Bots allows us to automate any kind of actions allowed by the exchanges APIs. In this example we'll create an automation that makes use of many API actions as well as the internal store of Trading Bots.

Any to Any is an automated payment gateway that allows us to watch for deposits in one currency or even for a specific address. Whenever a deposit is detected (and confirmed), the amount will be converted at market price to the desired currency. Finally an optional automatic withdrawal can be made.

This bot might be useful to vendors as they need the fiat money as soon as the coins are available to avoid volatility, also you can set it to withdraw the funds to your fiat account automatically.

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
- This bot makes use of a storage file. Default storage saves data as JSON objects inside store.json file found at the root of this project. This file could contain data essential for the correct execution of this strategy.


## Usage

For more references, go to the [official documentation](https://github.com/budacom/trading-bots/blob/master/README.md).

### Setup Config File

Found at `example_bots/any_to_any/configs` folder. Its a yaml file that allows us to easily set parameters.

**Example:**
```yml
from:
  currency: 'BTC'    # 3 digits currency code
  address: 'Any'     # 'Any' if fiat or every address
to:
  currency: 'CLP'    # 3 digits currency code
  withdraw: True     # True to withdraw converted amount
  address: 'None'    # 'None' if fiat
```

## Bot Strategy



### Setup

```python
def _setup(self, config):
    # Get configs
    self.from_currency = config['from']['currency']
    self.from_address = config['from']['address']
    self.to_currency = config['to']['currency']
    self.to_withdraw = config['to']['withdraw']
    self.to_address = config['to']['address']
    # Set market
    self.market = self._get_market(self.from_currency, self.to_currency)
    # Set side
    self.side = Side.SELL if self.market.base == self.from_currency else Side.BUY
    # Set buda trading client
    client_params = dict(timeout=self.timeout)
    self.buda = BudaTrading(self.market, client_params, self.dry_run, self.log, self.store)
    # Get deposits
    self.deposits = self.store.get(self.from_currency + '_deposits') or {}
    # Set start timestamp
    if self.store.get('start_timestamp'):
        self.start_timestamp = self.store.get('start_timestamp')
    else:
        self.start_timestamp = maya.now().epoch
        self.store.set('start_timestamp', self.start_timestamp)
```

- At setup we initialize our variables and clients according to the `market` built from our configs.

### Algorithm

We describe our instructions following our desired automation logic:

```python
def _algorithm(self):
    # Get new deposits
    self.log.info(f'Checking for new {self.from_currency} deposits')
    self.update_deposits()
    # Convert pending amounts
    self.log.info('Converting pending amounts')
    self.process_conversions()
    # Get available balances
    self.log.info('Processing pending withdrawals')
    self.process_withdrawals()
```


**Update deposits**

```python
def update_deposits(self):
    # Set wallet from relevant currency according to side
    from_wallet = self.buda.wallets.quote if self.side == Side.BUY else self.buda.wallets.base
    # Get and filter deposits
    new_deposits = from_wallet.fetch_deposits_since(self.start_timestamp)
    if self.from_address != 'Any':
        new_deposits = [deposit for deposit in new_deposits if deposit.data.address == self.from_address]
    # Update states on existing keys and add new keys with base structure
    for deposit in new_deposits:
        idx = str(deposit.id)
        if idx in self.deposits.keys():
            if deposit.status.value != self.deposits[idx]['status']:
                self.deposits[idx]['status'] = deposit.status
        else:
            self.deposits[idx] = {
                'status': deposit.status.value,
                'amounts': {'original_amount': repr(deposit.amount),
                            'converted_amount': repr(Money(0, self.from_currency)),
                            'converted_value': repr(Money(0, self.to_currency))},
                'orders': [],
                'pending_withdrawal': self.to_withdraw
            }
        self.store.set(self.from_currency + '_deposits', self.deposits)
```

- Get new deposits from the indicated `from_currency` on our configs.
- Add new deposits to store file indexed by id.

**Process conversions**

```python
def process_conversions(self):
    for deposit in self.deposits.values():
        # Calculate remaining amount to convert
        original_amount = Money.loads(deposit['amounts']['original_amount'])
        converted_amount = Money.loads(deposit['amounts']['converted_amount'])
        converted_value = Money.loads(deposit['amounts']['converted_value'])
        remaining = original_amount - converted_amount
        if self.side == Side.BUY:  # Change remaining amount to base currency for order creation purposes
            remaining = self.buda.fetch_order_book().quote(self.side, remaining).base_amount
        if deposit['status'] == TxStatus.OK.value and remaining > self.buda.min_order_amount:
            remaining = truncate_money(remaining)
            # Convert remaining amount using market order
            order = self.buda.place_market_order(self.side, remaining)
            # Wait for traded state to set updated values
            if order:
                self.log.info(f'{self.side} market order placed, waiting for traded state')
                while order.status != OrderStatus.CLOSED:
                    order = self.buda.fetch_order(order.id)
                    maya.time.sleep(1)
                self.log.info(f'{self.side} order traded, updating store values')
                if self.side == Side.BUY:
                    converted_amount += order.cost
                    converted_value += order.filled - order.fee
                if self.side == Side.SELL:
                    converted_amount += order.filled
                    converted_value += order.cost - order.fee
                deposit['orders'].append(order.id)  # Save related orders for debugging
            # Save new values __str__
            deposit['amounts']['converted_amount'] = repr(converted_amount)
            deposit['amounts']['converted_value'] = repr(converted_value)
    # Store all deposits
    self.store.set(self.from_currency + '_deposits', self.deposits)
```

- Checks if any deposit has pending amount to be converted.
- Creates market order for pending conversions.
- Saves converted amount and value on store file.

**Process withdrawals**

```python
def process_withdrawals(self):
    # Set wallet from relevant currency according to side
    to_wallet = self.buda.wallets.base if self.side == Side.BUY else self.buda.wallets.quote
    for deposit in self.deposits.values():
        # Load money amounts
        original_amount = Money.loads(deposit['amounts']['original_amount'])
        converted_amount = Money.loads(deposit['amounts']['converted_amount'])
        converted_value = Money.loads(deposit['amounts']['converted_value'])
        remaining = original_amount - converted_amount
        if self.side == Side.BUY:  # Change remaining amount to base currency for minimum order amount check
            remaining = self.buda.fetch_order_book().quote(self.side, remaining).base_amount
        # Filter deposits already converted and pending withdrawal
        original_amount_is_converted = remaining < self.buda.min_order_amount
        if deposit['status'] == TxStatus.OK.value and deposit['pending_withdrawal'] and original_amount_is_converted:
            withdrawal_amount = truncate_money(converted_value)
            available = to_wallet.fetch_balance().free
            if withdrawal_amount <= available:  # We cannot withdraw more than available balance
                w = to_wallet.request_withdrawal(withdrawal_amount, self.to_address, subtract_fee=True)
                if w.status == TxStatus.PENDING:  # Check state to set and store updated values
                    self.log.info(f'{self.to_currency} withdrawal request received, updating store values')
                    deposit['pending_withdrawal'] = False
                    self.store.set(self.from_currency + '_deposits', self.deposits)
                else:
                    self.log.warning('Withdrawal failed')
            else:
                self.log.warning(f'Available balance not enough for withdrawal amount {withdrawal_amount}')
```

- If `withdraw` is enabled on config file, withdraws pending value to desired wallet or fiat account.
- Saves result on store file.

### Abort

As important as our strategy is providing abort instructions which is the piece of code that executes in case anything goes wrong:

```python
def _abort(self):
    pass
```
- Nothing to rollback, just exit.

## Running bots

Test by running the desired bot once from console:
```bash
$ python bots.py run AnyToAny
```

Flag `--config` can be specified to change the default config file:
```bash
$ python bots.py run AnyToAny --config /path/to/any-to-any_other.yml
```

Now, we need this to run on a loop, we should use `loop` option indicating `--interval` as seconds:
```bash
$ python bots.py loop AnyToAny --interval 300
```

Running multiple bots for different markets is possible using multiple shells and config files:

Shell 1:
```bash
$ python bots.py loop AnyToAny --interval 300 --config any-to-any_btc_clp.yml
```
Shell 2:
```bash
$ python bots.py loop AnyToAny --interval 300 --config any-to-any__eth_btc.yml
```


## Contributing

Fork this code, BUIDL bots, submit a pull request :muscle:!
