from __future__ import annotations

import inspect
from inspect import signature, getmembers
from typing import Callable, get_type_hints, Type, Dict


import logging
import unittest

class TestReflection(unittest.TestCase):
    def test_1(self):
       self.assertEqual("hello", "hello")


if __name__ == '__main__':
    unittest.main()