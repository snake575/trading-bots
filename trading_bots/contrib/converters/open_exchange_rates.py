import trading_api_wrappers as api
from cached_property import cached_property

from .base import Converter

__all__ = [
    'OpenExchangeRates'
]


class OpenExchangeRates(Converter):
    name = 'OpenExchangeRates'

    @cached_property
    def client(self) -> api.OXR:
        return api.OXR(**self.client_params)

    def _get_rate(self, currency: str, to: str):
        response = self.client.latest(base=currency.lower(), symbols=[to.lower()])
        rate = response['rates'][to.upper()]
        return rate
