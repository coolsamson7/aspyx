"""
Test cases for the aspyx.di module.
"""
from __future__ import annotations

import threading
import time
import logging
import unittest
from typing import Dict
from di_import import ImportedModule, ImportedClass
from aspyx.di.configuration import EnvConfigurationSource

# not here

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s in %(filename)s:%(lineno)d - %(message)s'
)

def configure_logging(levels: Dict[str, int]) -> None:
    for name, level in levels.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)

        # If no handler is attached, add one
        if not logger.handlers and logger.propagate is False:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '[%(asctime)s] %(levelname)s in %(filename)s:%(lineno)d - %(message)s'
            ))
            logger.addHandler(handler)

configure_logging({"aspyx.di": logging.DEBUG})


from aspyx.di import DIException, injectable, order, on_init, on_running, on_destroy, inject_environment, inject, \
    Factory, create, module, Environment, PostProcessor, factory, requires_feature, conditional, requires_class, \
    requires_configuration, requires_configuration_value
from aspyx.di.configuration import ConfigurationSource, ConfigurationManager, config
from typing import Annotated



### TEST

@injectable()
@order(10)
class SamplePostProcessor(PostProcessor):
    def process(self, instance: object, environment: Environment):
        pass #print(f"created a {instance}")

class Baa:
    def init(self):
        pass

class Foo:
    def __init__(self):
        self.inited = False

    @on_init()
    def init(self):
        self.inited = True

class Baz:
    def __init__(self):
        self.inited = False

    @on_init()
    def init(self):
        self.inited = True

@injectable()
class Bazong:
    pass
    #def __init__(self):
    #    pass

class ConditionalBase:
    pass

@injectable()
@conditional(requires_feature("dev"))
class DevClass(ConditionalBase):
    def __init__(self):
        pass

@injectable()
@conditional(requires_class(DevClass))
class DevDependantClass:
    def __init__(self):
        pass

@injectable()
@conditional(requires_feature("prod"))
class ProdClass(ConditionalBase):
    def __init__(self):
        pass

@injectable()
@conditional(requires_class(ConditionalBase))
class RequiresBase:
    def __init__(self, base: ConditionalBase):
        pass

# Configuration conditional test classes

class TestConfigSource(ConfigurationSource):
    def load(self) -> dict:
        return {
            "database": {
                "host": "localhost",
                "port": 5432
            },
            "feature": {
                "enabled": True
            },
            "server": {
                "host": "0.0.0.0",
                "port": 8080,
                "timeout": 30
            },
            "api": {
                "key": "test-api-key-123"
            }
        }

@injectable()
@conditional(requires_configuration("database"))
class RequiresDatabaseConfig:
    def __init__(self):
        self.name = "database-service"

@injectable()
@conditional(requires_configuration("database.host"))
class RequiresDatabaseHostConfig:
    def __init__(self):
        self.name = "database-host-service"

@injectable()
@conditional(requires_configuration_value("feature.enabled", True))
class RequiresFeatureEnabled:
    def __init__(self, test: config(bool, "feature.enabled")):
        self.name = "feature-service"
        self.test = test  # Store for verification

# @inject with config() test classes

@injectable()
class ServiceWithInjectConfig:
    def __init__(self):
        self.host = None
        self.port = None

    @inject()
    def set_config(self, host: config(str, "database.host", "localhost"), port: config(int, "database.port", 5432)):
        self.host = host
        self.port = port

@module()
class InjectConfigTestModule:
    pass

# Automatic Environment injection test classes

@injectable()
class ServiceWithEnvironment:
    def __init__(self, env: Environment):
        self.env = env

@module()
class AutoEnvironmentTestModule:
    pass

@injectable()
class EnvironmentDependency:
    def __init__(self):
        self.name = "dependency"

@injectable()
class ServiceWithMixed:
    def __init__(self, dep: EnvironmentDependency, env: Environment, value: config(str, "test.value", "default")):
        self.dep = dep
        self.env = env
        self.value = value

@module()
class AutoEnvironmentMixedTestModule:
    pass

@injectable()
class FactoryWithEnvironment:
    @create()
    def create_service(self, env: Environment) -> str:
        return f"created-in-{env.type.__name__}"

@module()
class AutoEnvironmentFactoryTestModule:
    pass

@injectable()
@conditional(requires_configuration_value("feature.enabled", False))
class RequiresFeatureDisabled:
    def __init__(self):
        self.name = "feature-disabled-service"

# Annotation-based injection test classes - NOT injectable, we'll test them separately

class Base:
    def __init__(self):
        pass

class Ambiguous:
    def __init__(self):
        pass

class Unknown:
    def __init__(self):
        pass#

@injectable(scope="request")
class NonSingleton:
    def __init__(self):
        super().__init__()

@injectable()
class Derived(Ambiguous):
    def __init__(self):
        super().__init__()

@injectable()
class Derived1(Ambiguous):
    def __init__(self):
        super().__init__()

@injectable()
class Bar(Base):
    def __init__(self, foo: Foo):
        super().__init__()

        self.bazong = None
        self.baz = None
        self.foo = foo
        self.inited = False
        self.running = False
        self.destroyed = False
        self.environment = None

    @create()
    def create_baa(self) -> Baa:
        return Baa()

    @on_init()
    def init(self):
        self.inited = True

    @on_running()
    def set_running(self):
        self.running = True

    @on_destroy()
    def destroy(self):
        self.destroyed = True

    @inject_environment()
    def init_environment(self, env: Environment):
        self.environment = env

    @inject()
    def set(self, baz: Baz, bazong: Bazong) -> None:
        self.baz = baz
        self.bazong = bazong

@factory()
class SampleFactory(Factory[Foo]):
    __slots__ = []

    def __init__(self):
        pass

    def create(self) -> Foo:
        return Foo()

@module()
class SimpleModule:
    # constructor

    def __init__(self):
        pass

    #TEST
    @create()
    def create_config(self) -> EnvConfigurationSource:
        return EnvConfigurationSource()

    @create()
    def create_test_config(self) -> TestConfigSource:
        return TestConfigSource()

    # TES

    # create some beans

    @create()
    def create(self) -> Baz: #source: EnvConfigurationSource
        return Baz()

@module(imports=[SimpleModule, ImportedModule])
class ComplexModule:
    # constructor

    def __init__(self):
        pass

class TestDI(unittest.TestCase):
    testEnvironment = Environment(SimpleModule, features=["dev"])

    def test_thread_test(self):
        n_threads = 1
        iterations = 10000

        threads = []

        def worker(thread_id: int):
            env = Environment(SimpleModule, features=["dev"])

            for i in range(iterations):
                foo = env.get(Foo)

        for t_id in range(0, n_threads):
            thread = threading.Thread(target=worker, args=(t_id,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        print("All threads finished.")

    def test_conditional(self):
        env = TestDI.testEnvironment

        base = env.get(ConditionalBase)
        dev = env.get(DevClass)
        dep = env.get(DevDependantClass)

        try:
            env.get(ProdClass)
            self.fail("should not return conditional class")
        except Exception:
            pass

        self.assertIs(base, dev)
        self.assertIsNotNone(dev)
        self.assertIsNotNone(dep)

        # prod

        prod_environment = Environment(SimpleModule, features=["prod"])

        base = prod_environment.get(ConditionalBase)
        prod = prod_environment.get(ProdClass)

        self.assertIs(base, prod)
        self.assertIsNotNone(prod)

        print(prod_environment.report())

        # none

        try:
            no_feature_environment = Environment(SimpleModule)
            no_feature_environment = prod_environment.get(RequiresBase)
            self.fail("should not return conditional class")
        except Exception as e:
            pass

    def test_process_factory_instances(self):
        env = TestDI.testEnvironment

        print(env.report())
        print(env.parent.report())

        baz = env.get(Baz)
        foo = env.get(Foo)
        self.assertEqual(baz.inited, True)
        self.assertEqual(foo.inited, True)

    def test_baseclass(self):
        env = TestDI.testEnvironment

        bar = env.get(Bar)
        base = env.get(Base)

        self.assertIs(bar, base)

    def test_inject_base_class(self):
        env = TestDI.testEnvironment

        base = env.get(Base)
        self.assertEqual(type(base), Bar)

    def test_inject_ambiguous_class(self):
        with self.assertRaises(DIException):
            env = TestDI.testEnvironment
            env.get(Ambiguous)

    def test_create_unknown(self):
        with self.assertRaises(DIException):
            env = TestDI.testEnvironment
            env.get(Unknown)

    def test_inject_constructor(self):
        env = TestDI.testEnvironment

        bar = env.get(Bar)
        baz = env.get(Baz)
        bazong = env.get(Bazong)
        foo = env.get(Foo)

        self.assertIsNotNone(bar)
        self.assertIs(bar.foo, foo)
        self.assertIs(bar.baz, baz)
        self.assertIs(bar.bazong, bazong)

    def test_factory(self):
        env = TestDI.testEnvironment
        foo = env.get(Foo)
        self.assertIsNotNone(foo)

    def test_create_factory(self):
        env = TestDI.testEnvironment
        baz = env.get(Baz)
        baa= env.get(Baa)
        self.assertIsNotNone(baz)
        self.assertIsNotNone(baa)

    def test_singleton(self):
        env = TestDI.testEnvironment

        # injectable

        bar = env.get(Bar)
        bar1 = env.get(Bar)
        self.assertIs(bar, bar1)

        # factory

        foo = env.get(Foo)
        foo1 = env.get(Foo)
        self.assertIs(foo,foo1)

        # create

        baz  = env.get(Baz)
        baz1 = env.get(Baz)
        self.assertIs(baz, baz1)

    def test_non_singleton(self):
        env = TestDI.testEnvironment

        ns = env.get(NonSingleton)
        ns1 = env.get(NonSingleton)

        self.assertIsNot(ns, ns1)

    def test_import_configurations(self):
        env = Environment(ImportedModule)

        imported = env.get(ImportedClass)
        self.assertIsNotNone(imported)

    def test_init(self):
        env = TestDI.testEnvironment

        bar = env.get(Bar)

        self.assertEqual(bar.inited, True)

    def test_running(self):
        env = TestDI.testEnvironment

        bar = env.get(Bar)

        self.assertEqual(bar.running, True)

    def test_destroy(self):
        env = TestDI.testEnvironment

        bar = env.get(Bar)

        env.destroy()

        self.assertEqual(bar.destroyed, True)

    def test_performance(self):
        env = TestDI.testEnvironment

        start = time.perf_counter()
        for _ in range(1000000):
            env.get(Bar)

        end = time.perf_counter()

        avg_ms = ((end - start) / 1000000) * 1000
        print(f"Average time per Bar creation: {avg_ms:.3f} ms")

    def test_configuration_conditional(self):
        """Test requires_configuration and requires_configuration_value conditionals"""
        # Create a fresh environment to pick up the test config
        env = Environment(SimpleModule, features=["dev"])

        # Test requires_configuration with inner node
        db_service = env.get(RequiresDatabaseConfig)
        self.assertIsNotNone(db_service)
        self.assertEqual(db_service.name, "database-service")

        # Test requires_configuration with leaf value
        db_host_service = env.get(RequiresDatabaseHostConfig)
        self.assertIsNotNone(db_host_service)
        self.assertEqual(db_host_service.name, "database-host-service")

        # Test requires_configuration_value with matching value
        feature_service = env.get(RequiresFeatureEnabled)
        self.assertIsNotNone(feature_service)
        self.assertEqual(feature_service.name, "feature-service")
        # Verify config value was injected correctly
        self.assertEqual(feature_service.test, True)
        self.assertIsInstance(feature_service.test, bool)

        # Test requires_configuration_value with non-matching value (should not be registered)
        try:
            env.get(RequiresFeatureDisabled)
            self.fail("RequiresFeatureDisabled should not be registered")
        except DIException:
            pass  # Expected

        env.destroy()

    def test_annotation_injection(self):
        """Test annotation-based configuration injection using new config() shortcut"""
        # Test get_annotated_params with new config(type, key) syntax
        from aspyx.reflection import TypeDescriptor
        from aspyx.di.configuration import config, ConfigValue

        # Create a proper class with annotated method using new syntax
        class TestClass:
            def test_method(
                self,
                host: config(str, "server.host"),
                port: config(int, "server.port"),
                regular_param: str
            ):
                pass

        descriptor = TypeDescriptor.for_type(TestClass)
        method_desc = descriptor.get_method("test_method")

        annotated_params = method_desc.get_annotated_params()

        # Verify we got 3 parameters
        self.assertEqual(len(annotated_params), 3)

        # First param should have ConfigValue metadata
        self.assertEqual(annotated_params[0].name, "host")
        self.assertEqual(annotated_params[0].type, str)
        self.assertEqual(len(annotated_params[0].metadata), 1)
        self.assertIsInstance(annotated_params[0].metadata[0], ConfigValue)
        self.assertEqual(annotated_params[0].metadata[0].key, "server.host")

        # Second param should have ConfigValue metadata
        self.assertEqual(annotated_params[1].name, "port")
        self.assertEqual(annotated_params[1].type, int)
        self.assertEqual(len(annotated_params[1].metadata), 1)
        self.assertIsInstance(annotated_params[1].metadata[0], ConfigValue)
        self.assertEqual(annotated_params[1].metadata[0].key, "server.port")

        # Third param should have no metadata
        self.assertEqual(annotated_params[2].name, "regular_param")
        self.assertEqual(annotated_params[2].type, str)
        self.assertEqual(len(annotated_params[2].metadata), 0)

    def test_config_shortcuts(self):
        """Test that config() shortcut works correctly with type parameter"""
        # Test config() with type parameter
        from aspyx.di.configuration import config, ConfigValue
        from typing import get_origin, get_args
        import typing

        # Test config(str, ...)
        str_type = config(str, "server.host", "localhost")
        self.assertEqual(get_origin(str_type), typing.Annotated)
        args = get_args(str_type)
        self.assertEqual(args[0], str)  # Base type
        self.assertIsInstance(args[1], ConfigValue)  # Metadata
        self.assertEqual(args[1].key, "server.host")
        self.assertEqual(args[1].default, "localhost")

        # Test config(int, ...)
        int_type = config(int, "server.port", 8080)
        self.assertEqual(get_origin(int_type), typing.Annotated)
        args = get_args(int_type)
        self.assertEqual(args[0], int)
        self.assertEqual(args[1].key, "server.port")
        self.assertEqual(args[1].default, 8080)

        # Test config(bool, ...)
        bool_type = config(bool, "feature.enabled", False)
        self.assertEqual(get_origin(bool_type), typing.Annotated)
        args = get_args(bool_type)
        self.assertEqual(args[0], bool)
        self.assertEqual(args[1].key, "feature.enabled")
        self.assertEqual(args[1].default, False)

        # Test config(float, ...)
        float_type = config(float, "server.timeout", 30.0)
        self.assertEqual(get_origin(float_type), typing.Annotated)
        args = get_args(float_type)
        self.assertEqual(args[0], float)
        self.assertEqual(args[1].key, "server.timeout")
        self.assertEqual(args[1].default, 30.0)

    def test_inject_with_config(self):
        """Test that @inject() works with config() annotation-based parameters"""

        env = Environment(InjectConfigTestModule)

        # Get service and verify config was injected via @inject method
        # Values come from TestConfigSource which is created in SimpleModule
        service = env.get(ServiceWithInjectConfig)
        self.assertIsNotNone(service)
        # TestConfigSource provides these values
        self.assertEqual(service.host, "localhost")
        self.assertEqual(service.port, 5432)

    def test_automatic_environment_injection(self):
        """Test that Environment type parameters are automatically injected"""

        env = Environment(AutoEnvironmentTestModule)

        # Get service and verify environment was injected
        service = env.get(ServiceWithEnvironment)
        self.assertIsNotNone(service)
        self.assertIsInstance(service.env, Environment)
        self.assertIs(service.env, env)  # Should be the exact same instance

    def test_automatic_environment_injection_with_other_params(self):
        """Test Environment injection works alongside other DI parameters"""

        env = Environment(AutoEnvironmentMixedTestModule)

        # Get service and verify all parameters were injected correctly
        service = env.get(ServiceWithMixed)
        self.assertIsNotNone(service)
        self.assertIsInstance(service.dep, EnvironmentDependency)
        self.assertEqual(service.dep.name, "dependency")
        self.assertIsInstance(service.env, Environment)
        self.assertIs(service.env, env)
        self.assertEqual(service.value, "default")

    def test_automatic_environment_injection_in_factory_methods(self):
        """Test Environment injection in @create factory methods"""

        env = Environment(AutoEnvironmentFactoryTestModule)

        # Get the created string
        result = env.get(str)
        self.assertEqual(result, f"created-in-{AutoEnvironmentFactoryTestModule.__name__}")


if __name__ == '__main__':
    unittest.main()
