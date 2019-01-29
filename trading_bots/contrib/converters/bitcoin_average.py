import requests

from .base import Converter

__all__ = [
    'BitcoinAverage'
]


class BitcoinAverage(Converter):
    name = 'Bitcoin Average'
    base_url = 'https://apiv2.bitcoinaverage.com'
    symbol_set = 'global'

    def _get_rate(self, currency: str, to: str):
        symbol = (currency + to).upper()
        url = f'{self.base_url}/indices/{self.symbol_set}/ticker/{symbol}'
        response = requests.get(url).json()
        rate = response['last']
        return rate
