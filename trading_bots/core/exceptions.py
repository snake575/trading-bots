"""
Global Trading-Bots exception and warning classes.
"""


class AppRegistryNotReady(Exception):
    """The trading_bots.bots registry is not populated yet"""

    pass


class ImproperlyConfigured(Exception):
    """Trading-Bots is somehow improperly configured"""

    pass
