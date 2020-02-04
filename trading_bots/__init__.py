def setup():
    """
    Configure the settings (this happens as a side effect of accessing the
    first setting), configure logging and populate the app registry.
    """
    from trading_bots.bots import bots
    from trading_bots.conf import settings

    bots.populate(settings.installed_bots)
