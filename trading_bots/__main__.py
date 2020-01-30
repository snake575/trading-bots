"""
Invokes bots when the trading_bots module is run as a script.
Example: python -m trading_bots --help
"""
from trading_bots.core import management

if __name__ == "__main__":
    management.cli()
