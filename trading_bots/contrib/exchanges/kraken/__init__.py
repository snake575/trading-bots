from ..base import Exchange
from .clients import *

__all__ = [
    "Kraken",
]


class Kraken(Exchange, KrakenPublic):
    market_client = KrakenMarket
    wallet_client = KrakenWallet
    trading_client = KrakenTrading
