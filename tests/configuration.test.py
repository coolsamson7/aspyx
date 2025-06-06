from __future__ import annotations

import unittest

from aspyx.configuration import ConfigurationSource, ConfigurationManager, value

from aspyx.di import component, Environment


@component()
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

@component()
class Foo:
    @value("b.d", 0)
    def set_foo(self, value: int):
        self.value = value

class TestConfiguration(unittest.TestCase):
    def testInjection(self):
       env = Environment()

def suite():
    suite = unittest.TestSuite()

    suite.addTest(unittest.makeSuite(TestConfiguration))

    return suite


if __name__ == '__main__':
    #unittest.main()
    runner = unittest.TextTestRunner()
    runner.run(suite())