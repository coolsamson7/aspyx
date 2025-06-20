"""
Tests
"""
from __future__ import annotations

import unittest

from aspyx.di import injectable, module, Environment
from aspyx.di.di import DIException


@injectable()
class Foo:
    def __init__(self, foo: Bar):
        pass

@injectable()
class Bar:
    def __init__(self, foo: Foo):
        pass

@module()
class SampleModule:
    # constructor

    def __init__(self):
        pass

class TestCycle(unittest.TestCase):
    def test_cycle(self):
        with self.assertRaises(DIException):
            Environment(SampleModule)


if __name__ == '__main__':
    unittest.main()
