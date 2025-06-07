from __future__ import annotations

import unittest

from aspyx.configuration import ConfigurationSource, ConfigurationManager, value, ConfigurationConfiguration

from aspyx.di import injectable, Environment, configuration, CallableProcessor


@configuration(imports=[ConfigurationConfiguration])
class Configuration:
    def __init__(self):
        pass

@injectable()
class SampleConfigurationSource(ConfigurationSource):
    # constructor

    def __init__(self, manager: ConfigurationManager):
        super().__init__(manager)


    def load(self) -> dict:
        return {
            "a": 1, 
            "b": {
                "d": "2", 
                "e": 3, 
                "f": 4
                }
            }

@injectable()
class Foo:
    def __init__(self, manager: ConfigurationManager):
        manager.load()

    @value("b.d", 0)
    def set_foo(self, value: int):
        self.value = value

class TestConfiguration(unittest.TestCase):
    def testInjection(self):
        env = Environment(Configuration)
        foo = env.get(Foo)
        self.assertEqual(foo.value, 2)


if __name__ == '__main__':
    unittest.main()