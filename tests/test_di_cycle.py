from __future__ import annotations

import unittest

from aspyx.di import injectable, environment, Environment
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

@environment()
class TestEnvironment:
    # constructor

    def __init__(self):
        pass

class TestCycle(unittest.TestCase):
    def test_cycle(self):
        pass #with self.assertRaises(InjectorException):
        #    env = Environment(TestEnvironment)


if __name__ == '__main__':
   unittest.main()