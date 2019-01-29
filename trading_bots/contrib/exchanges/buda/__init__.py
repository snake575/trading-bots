from .clients import *
from ..base import Exchange

__all__ = [
    'Buda',
]


class Buda(Exchange, BudaPublic):
    market_client = BudaMarket
    wallet_client = BudaWallet
    trading_client = BudaTrading
