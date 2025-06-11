from __future__ import annotations

import time
import logging
import unittest
from typing import Dict

from aspyx.di import InjectorException, injectable, on_init, on_destroy, inject_environment, inject, Factory, create, environment, Environment, PostProcessor, factory
from aspyx.di.di import order
from di_import import ImportedEnvironment, ImportedClass

# not here

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(filename)s:%(lineno)d - %(message)s'
)

def configure_logging(levels: Dict[str, int]) -> None:
    for name in levels:
        logging.getLogger(name).setLevel(levels[name])

configure_logging({
    "aspyx": logging.DEBUG
})

# not here


@injectable()
@order(10)
class SamplePostProcessor(PostProcessor):
    def process(self, instance: object, environment: Environment):
        pass #print(f"created a {instance}")

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

    pass

@injectable()
class Bazong:
    def __init__(self, foo: Foo):
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
        self.destroyed = False
        self.environment = None

    @on_init()
    def init(self):
        self.inited = True

    @on_destroy()
    def destroy(self):
        self.destroyed = True

    @inject_environment()
    def initEnvironment(self, env: Environment):
        self.environment = env

    @inject()
    def set(self, baz: Baz, bazong: Bazong) -> None:
        self.baz = baz
        self.bazong = bazong

@factory()
class TestFactory(Factory[Foo]):
    __slots__ = []

    def __init__(self):
        pass

    def create(self) -> Foo:
        return Foo()

@environment()
class SimpleEnvironment:
    # constructor

    def __init__(self):
        pass

    # create some beans

    @create()
    def create(self) -> Baz:
        return Baz()

@environment(imports=[SimpleEnvironment, ImportedEnvironment])
class TestEnvironment:
    # constructor

    def __init__(self):
        pass

class TestInject(unittest.TestCase):
    testEnvironment = Environment(SimpleEnvironment)


    def test_process_factory_instances(self):
        env = TestInject.testEnvironment

        baz = env.get(Baz)
        foo = env.get(Foo)
        self.assertEqual(baz.inited, True)
        self.assertEqual(foo.inited, True)

    def test_inject_base_class(self):
        env = TestInject.testEnvironment

        base = env.get(Base)
        self.assertEqual(type(base), Bar)

    def test_inject_ambiguous_class(self):
        with self.assertRaises(InjectorException):
            env = TestInject.testEnvironment
            env.get(Ambiguous)

    def test_create_unknown(self):
        with self.assertRaises(InjectorException):
            env = TestInject.testEnvironment
            env.get(Unknown)

    def test_inject_constructor(self):
        env = TestInject.testEnvironment

        bar = env.get(Bar)
        baz = env.get(Baz)
        bazong = env.get(Bazong)
        foo = env.get(Foo)

        self.assertIsNotNone(bar)
        self.assertIs(bar.foo, foo)
        self.assertIs(bar.baz, baz)
        self.assertIs(bar.bazong, bazong)

    def test_factory(self):
        env = TestInject.testEnvironment
        foo = env.get(Foo)
        self.assertIsNotNone(foo)

    def test_create_factory(self):
        env = TestInject.testEnvironment
        baz = env.get(Baz)
        self.assertIsNotNone(baz)

    def test_singleton(self):
        env = TestInject.testEnvironment

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
        env = TestInject.testEnvironment

        ns = env.get(NonSingleton)
        ns1 = env.get(NonSingleton)

        self.assertIsNot(ns, ns1)

    #def test_import_configurations(self): TODO
    #    env = Environment(TestEnvironment)#

    #    imported = env.get(ImportedClass)

    #    self.assertIsNotNone(imported)

    def test_init(self):
        env = TestInject.testEnvironment

        bar = env.get(Bar)

        self.assertEqual(bar.inited, True)

    def test_destroy(self):
        env = TestInject.testEnvironment

        bar = env.get(Bar)

        env.destroy()

        self.assertEqual(bar.destroyed, True)

    def test_performance(self):
        env = TestInject.testEnvironment

        start = time.perf_counter()
        for _ in range(1000000):
            bar = env.get(Bar)
        end = time.perf_counter()

        avg_ms = ((end - start) / 1000000) * 1000
        print(f"Average time per Bar creation: {avg_ms:.3f} ms")


if __name__ == '__main__':
   unittest.main()