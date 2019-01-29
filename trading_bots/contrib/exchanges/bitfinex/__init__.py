from .clients import *
from ..base import Exchange

__all__ = [
    'Bitfinex',
]


class Bitfinex(Exchange, BitfinexPublic):
    market_client = BitfinexMarket
    wallet_client = BitfinexWallet
    trading_client = BitfinexTrading
