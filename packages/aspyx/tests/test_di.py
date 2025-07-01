"""
Test cases for the aspyx.di module.
"""
from __future__ import annotations

import threading
import time
import logging
import unittest
from typing import Dict

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
    Factory, create, module, Environment, PostProcessor, factory, requires_feature, conditional, requires_class

from di_import import ImportedModule, ImportedClass

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
    def __init__(self):
        pass

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
            print(e)
            pass

    def test_process_factory_instances(self):
        env = TestDI.testEnvironment

        print(env.report())
        print(env.parent.report())

        baz = env.get(Baz)
        foo = env.get(Foo)
        self.assertEqual(baz.inited, True)
        self.assertEqual(foo.inited, True)

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


if __name__ == '__main__':
    unittest.main()
