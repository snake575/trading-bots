import trading_api_wrappers as api
from cached_property import cached_property

from .base import Converter

__all__ = [
    'CoinMarketCap'
]


class CoinMarketCap(Converter):
    name = 'CoinMarketCap'

    @cached_property
    def client(self) -> api.CoinMarketCap:
        return api.CoinMarketCap(**self.client_params)

    def _get_rate(self, currency: str, to: str):
        rate = self.client.price(currency, convert=to)
        return rate
