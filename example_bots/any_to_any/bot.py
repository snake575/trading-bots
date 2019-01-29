import maya

from trading_bots.bots import Bot
from trading_bots.contrib.exchanges.buda.clients import BudaTrading, BudaPublic
from trading_bots.contrib.models import Market, Side, Money, TxStatus, OrderStatus
from trading_bots.utils import truncate_money


class AnyToAny(Bot):
    label = 'AnyToAny'

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

    def _abort(self):
        pass

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

    def _get_market(self, from_currency, to_currency):
        buda_markets = BudaPublic().markets
        bases = [market.base for market in buda_markets]
        quotes = [market.quote for market in buda_markets]

        if from_currency in bases and to_currency in quotes:
            market = Market(from_currency, to_currency)
        elif from_currency in quotes and to_currency in bases:
            market = Market(to_currency, from_currency)
        else:
            raise NotImplementedError(f'No compatible market found!')
        return market
