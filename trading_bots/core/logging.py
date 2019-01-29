import logging
import time
from logging import Logger

import pygogo

# Set time to UTC
logging.Formatter.converter = time.gmtime

# Set default log format
DEFAULT_CONSOLE_FORMAT = '%(asctime)s UTC | %(name)s | %(levelname)-8s | %(message)s'

# Set formatter
formatter = logging.Formatter(DEFAULT_CONSOLE_FORMAT)

# Initialize pygogo logger
going = pygogo.Gogo(
    name='tradingbots',
    low_formatter=formatter,
    high_formatter=formatter,
    verbose=True,
    monolog=True,
)


def get_logger(name: str='base') -> Logger:
    return going.get_logger(name)
