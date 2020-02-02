from ..base import Exchange
from .clients import *

__all__ = [
    "Buda",
]


class Buda(Exchange, BudaPublic):
    market_client = BudaMarket
    wallet_client = BudaWallet
    trading_client = BudaTrading
