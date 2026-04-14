"""
Logging utilities for the Onshape API client.
Python 3 port of onshape-public-apikey/python/apikey/utils.py
"""

import logging

__all__ = ['log']

logger = logging.getLogger('onshape_api')


def log(msg, level=0):
    """Log a message. level=0 for info, level=1 for error."""
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('[%(levelname)s]: %(asctime)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    if level == 0:
        logger.info(msg)
    else:
        logger.error(msg)
