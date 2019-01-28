from dataclasses import dataclass
from typing import Dict, List

import maya

from trading_bots.bots import Bot
from trading_bots.contrib.exchanges.buda.clients import BudaTrading, BudaPublic
from trading_bots.contrib.models import Market, Side, Money, TxStatus, OrderStatus
from trading_bots.utils import truncate_money


@dataclass
class Deposit:
    status: TxStatus
    original_amount: Money
    converted_amount: Money
    converted_value: Money
    order_ids: List[str]
    withdrawal_pending: bool

    def serialize(self) -> Dict:
        return {
            'status': self.status.name,
            'original_amount': repr(self.original_amount),
            'converted_amount': repr(self.converted_amount),
            'converted_value': repr(self.converted_value),
            'orders': self.order_ids,
            'withdrawal_pending': self.withdrawal_pending,
        }

    @classmethod
    def deserialize(cls, deposit: Dict) -> 'Deposit':
        return cls(
            status=TxStatus(deposit['status']),
            original_amount=Money.loads(deposit['original_amount']),
            converted_amount=Money.loads(deposit['converted_amount']),
            converted_value=Money.loads(deposit['converted_value']),
            order_ids=deposit['order_ids'],
            withdrawal_pending=deposit['withdrawal_pending'],
        )


Deposits = Dict[str, Deposit]


class AnyToAny(Bot):
    label = 'AnyToAny'

    def _setup(self, config: Dict):
        # Get configs
        self.from_currency: str = config['from']['currency']
        self.from_address: str = config['from']['address']
        self.to_currency: str = config['to']['currency']
        self.to_withdraw: bool = config['to']['withdraw']
        self.to_address: str = config['to']['address']
        # Set market
        self.market = self._get_market(self.from_currency, self.to_currency)
        # Set side
        self.side = Side.SELL if self.market.base == self.from_currency else Side.BUY
        # Set buda trading client
        client_params = dict(timeout=self.timeout)
        self.buda = BudaTrading(self.market, client_params, self.dry_run, self.log, self.store)
        # Get deposits
        self.deposits = self._get_deposits_from_store()
        # Set start timestamp
        self.start_timestamp = self.store.get('start_timestamp')
        if not self.start_timestamp:
            self.start_timestamp = maya.now().epoch
            self.store.set('start_timestamp', self.start_timestamp)

    def _algorithm(self):
        # Get new deposits
        self.log.info(f'Checking for new {self.from_currency} deposits')
        self._update_deposits()
        # Convert pending amounts
        self.log.info('Converting pending amounts')
        self._process_conversions()
        # Get available balances
        self.log.info('Processing pending withdrawals')
        self._process_withdrawals()

    def _update_deposits(self):
        # Set wallet from relevant currency according to side
        from_wallet = self.buda.wallets.quote if self.side == Side.BUY else self.buda.wallets.base
        # Get and filter deposits
        buda_deposits = from_wallet.fetch_deposits_since(self.start_timestamp)
        if self.from_address != 'Any':
            buda_deposits = [deposit for deposit in buda_deposits if deposit.data.address == self.from_address]
        # Update states on existing keys and add new keys with base structure
        for buda_deposit in buda_deposits:
            if buda_deposit.id in self.deposits.keys():
                if buda_deposit.status != self.deposits[buda_deposit.id].status:
                    self.deposits[buda_deposit.id].status = buda_deposit.status
            else:
                self.deposits[buda_deposit.id] = Deposit(
                    status=buda_deposit.status,
                    original_amount=buda_deposit.amount,
                    converted_amount=Money(0, self.from_currency),
                    converted_value=Money(0, self.to_currency),
                    order_ids=[],
                    withdrawal_pending=self.to_withdraw,
                )
        # Save all deposits
        self._save_deposits_to_store(self.deposits)

    def _process_conversions(self):
        for deposit in self.deposits.values():
            # Calculate remaining amount to convert
            remaining = deposit.original_amount - deposit.converted_amount
            if self.side == Side.BUY:  # Change remaining amount to base currency for order creation purposes
                remaining = self.buda.fetch_order_book().quote(self.side, remaining).base_amount
            if deposit.status == TxStatus.OK and remaining > self.buda.min_order_amount:
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
                        deposit.converted_amount += order.cost
                        deposit.converted_value += order.filled - order.fee
                    if self.side == Side.SELL:
                        deposit.converted_amount += order.filled
                        deposit.converted_value += order.cost - order.fee
                    deposit.order_ids.append(order.id)  # Save related orders for debugging
        # Save all deposits
        self._save_deposits_to_store(self.deposits)

    def _process_withdrawals(self):
        # Set wallet from relevant currency according to side
        to_wallet = self.buda.wallets.base if self.side == Side.BUY else self.buda.wallets.quote
        for deposit in self.deposits.values():
            # Load money amounts
            remaining = deposit.original_amount - deposit.converted_amount
            if self.side == Side.BUY:  # Change remaining amount to base currency for minimum order amount check
                remaining = self.buda.fetch_order_book().quote(self.side, remaining).base_amount
            # Filter deposits already converted and pending withdrawal
            original_amount_is_converted = remaining < self.buda.min_order_amount
            if deposit.status == TxStatus.OK and deposit.withdrawal_pending and original_amount_is_converted:
                withdrawal_amount = truncate_money(deposit.converted_value)
                available = to_wallet.fetch_balance().free
                if withdrawal_amount <= available:  # We cannot withdraw more than available balance
                    w = to_wallet.request_withdrawal(withdrawal_amount, self.to_address, subtract_fee=True)
                    if w.status == TxStatus.PENDING:  # Check state to set and store updated values
                        self.log.info(f'{self.to_currency} withdrawal request received, updating store values')
                        deposit.withdrawal_pending = False
                        self.store.set(self.from_currency + '_deposits', self.deposits)
                    else:
                        self.log.warning('Withdrawal failed')
                else:
                    self.log.warning(f'Available balance not enough for withdrawal amount {withdrawal_amount}')

    def _get_market(self, from_currency: str, to_currency: str) -> Market:
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

    def _get_deposits_from_store(self) -> Deposits:
        name = f'{self.from_currency}_deposits'
        stored_deposits: Dict = self.store.get(name) or {}
        return {key: Deposit.deserialize(value) for key, value in stored_deposits.items()}

    def _save_deposits_to_store(self, deposits: Deposits):
        name = f'{self.from_currency}_deposits'
        serialized_deposits = {key: deposit.serialize() for key, deposit in deposits.items()}
        self.store.set(name, serialized_deposits)
