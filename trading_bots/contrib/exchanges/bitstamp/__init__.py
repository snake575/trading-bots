from ..base import Exchange
from .clients import *

__all__ = [
    "Bitstamp",
]


class Bitstamp(Exchange, BitstampPublic):
    market_client = BitstampMarket
    wallet_client = BitstampWallet
    trading_client = BitstampTrading
