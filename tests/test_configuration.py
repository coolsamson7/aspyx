"""
Test cases for the Configuration system in aspyx.di
"""
from __future__ import annotations

import unittest
from pathlib import Path

from aspyx.di.configuration import ConfigurationSource, ConfigurationManager, inject_value, EnvConfigurationSource, \
    YamlConfigurationSource

from aspyx.di import injectable, Environment, module, create


@module()
class SampleModule:
    # constructor

    def __init__(self):
        pass

    @create()
    def create_env_source(self) -> EnvConfigurationSource:
        return EnvConfigurationSource()

    @create()
    def create_yaml_source(self) -> YamlConfigurationSource:
        return YamlConfigurationSource(f"{Path(__file__).parent}/config.yaml"
)

@injectable()
class SampleConfigurationSource1(ConfigurationSource):
    # constructor

    def __init__(self):
        super().__init__()

    def load(self) -> dict:
        return {
            "a": 1, 
            "b": {}
            }

@injectable()
class SampleConfigurationSource2(ConfigurationSource):
    # constructor

    def __init__(self):
        super().__init__()

    def load(self) -> dict:
        return {
            "b": {
                "d": "2", 
                "e": 3, 
                "f": 4
                }
            }

@injectable(scope="request")
class Foo:
    def __init__(self):
        self.value = None
        self.value1 = None
        self.value2 = None

    @inject_value("b.d", 0)
    def set_value(self, value: int):
        self.value = value

    # will coerce
    @inject_value("b.e", 0)
    def set_value1(self, value: str):
        self.value1 = value

    @inject_value("b.z", "unknown")
    def set_value2(self, value: str):
        self.value2 = value

class TestConfiguration(unittest.TestCase):
    testEnvironment = Environment(SampleModule)

    def test_yaml(self):
        env = TestConfiguration.testEnvironment

        config = env.get(ConfigurationManager)

        port = config.get("server.port", int)
        self.assertEqual(port, 8000)

    def test_env(self):
        env = TestConfiguration.testEnvironment

        config = env.get(ConfigurationManager)

        os = config.get("HOME", str)
        self.assertIsNotNone(os)

    def test_configuration(self):
        env = TestConfiguration.testEnvironment

        config = env.get(ConfigurationManager)
        v1 = config.get("b.d", str)
        v2 = config.get("b.e", int, )
        v3 = config.get("b.z", str, "unknown")

        self.assertEqual(v1, "2")
        self.assertEqual(v2, 3)
        self.assertEqual(v3, "unknown")

    def test_configuration_injection(self):
        env = TestConfiguration.testEnvironment

        foo = env.get(Foo)

        self.assertEqual(foo.value, 2)

    def test_configuration_injection_coercion(self):
        env = TestConfiguration.testEnvironment

        foo = env.get(Foo)

        self.assertEqual(foo.value1, "3")

    def test_configuration_injection_default(self):
        env = TestConfiguration.testEnvironment

        foo = env.get(Foo)

        self.assertEqual(foo.value2, "unknown")


if __name__ == '__main__':
    unittest.main()
