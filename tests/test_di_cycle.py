from __future__ import annotations

import unittest

from aspyx.di import injectable, configuration, Environment
from aspyx.di.di import InjectorException


@injectable()
class Foo:
    def __init__(self, foo: Bar):
        pass
    pass

@injectable()
class Bar:
    def __init__(self, foo: Foo):
        pass

@configuration()
class Configuration:
    # constructor

    def __init__(self):
        pass

class TestCycle(unittest.TestCase):
    def test_cycle(self):
        with self.assertRaises(InjectorException):
            env = Environment(Configuration)


if __name__ == '__main__':
   unittest.main()