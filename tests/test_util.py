"""
Tests for sftdyn utility functions.
"""

from __future__ import annotations

import logging
import unittest

from sftdyn.util import clamp, log_setup


class TestUtil(unittest.TestCase):
    def test_clamp(self) -> None:
        self.assertEqual(clamp(5, 0, 10), 5)
        self.assertEqual(clamp(-5, 0, 10), 0)
        self.assertEqual(clamp(15, 0, 10), 10)
        self.assertEqual(clamp(0, 0, 10), 0)
        self.assertEqual(clamp(10, 0, 10), 10)

    def test_log_setup(self) -> None:
        logger = log_setup(0, default=1)
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, "sftdyn")
        self.assertEqual(logger.level, logging.WARNING)

        # Test increasing verbosity
        logger = log_setup(1, default=1)
        self.assertEqual(logger.level, logging.INFO)

        logger = log_setup(2, default=1)
        self.assertEqual(logger.level, logging.DEBUG)


if __name__ == "__main__":
    unittest.main()
