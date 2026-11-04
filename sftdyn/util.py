"""
Various utility functions.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("sftdyn")


def log_setup(setting: int, default: int = 1) -> logging.Logger:
    """
    Perform setup for the logger.
    Run before any logging thingy is called.

    if setting is 0: the default is used, which is WARNING.
    else: setting + default is used.
    """
    levels = (
        logging.ERROR,
        logging.WARNING,
        logging.INFO,
        logging.DEBUG,
        logging.NOTSET,
    )

    factor = clamp(default + setting, 0, len(levels) - 1)
    level = levels[factor]

    logging.basicConfig(level=level, format="[%(asctime)s] %(levelname)s: %(message)s")
    logger.setLevel(level)
    logger.info("Log level set to: %s", logging.getLevelName(level))
    logging.captureWarnings(True)
    return logger


def clamp(number: int, smallest: int, largest: int) -> int:
    """Return number but limit it to the inclusive given value range."""
    return max(smallest, min(number, largest))
