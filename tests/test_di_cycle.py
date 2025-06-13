"""
Tests
"""
from __future__ import annotations

import unittest

from aspyx.di import injectable, environment, Environment
from aspyx.di.di import DIException


@injectable()
class Foo:
    def __init__(self, foo: Bar):
        pass

@injectable()
class Bar:
    def __init__(self, foo: Foo):
        pass

@environment()
class SampleEnvironment:
    # constructor

    def __init__(self):
        pass

class TestCycle(unittest.TestCase):
    def test_cycle(self):
        with self.assertRaises(DIException):
            Environment(SampleEnvironment)


if __name__ == '__main__':
    unittest.main()
