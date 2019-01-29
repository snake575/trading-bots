import abc
from typing import Type, Union

from ..clients import *
from ..models import *

__all__ = [
    'Exchange',
]


class Exchange(BaseClient, abc.ABC):
    market_client: Type[MarketClient] = None
    wallet_client: Type[WalletClient] = None
    trading_client: Type[TradingClient] = None

    def __repr__(self):
        return f'Exchange({self.name})'

    def __str__(self):
        return self.name

    def Market(self, market: Union[str, Market]) -> MarketClient:
        return self.market_client(market, self.client_params, self.dry_run, self.log, self.store, self.name)

    def Wallet(self, currency: str) -> WalletClient:
        return self.wallet_client(currency, self.client_params, self.dry_run, self.log, self.store, self.name)

    def Trading(self, market: Union[str, Market]) -> TradingClient:
        return self.trading_client(market, self.client_params, self.dry_run, self.log, self.store, self.name)
