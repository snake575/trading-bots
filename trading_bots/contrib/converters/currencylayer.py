import trading_api_wrappers as api
from cached_property import cached_property

from .base import Converter

__all__ = [
    'CurrencyLayer'
]


class CurrencyLayer(Converter):
    name = 'Currencylayer'

    @cached_property
    def client(self) -> api.CurrencyLayer:
        return api.CurrencyLayer(**self.client_params)

    def _get_rate(self, currency: str, to: str):
        market = (currency + to).upper()
        response = self.client.live_rates(base=currency.lower(), currencies=[to.lower()])
        rate = response['quotes'][market]
        return rate
