from __future__ import annotations

import time
import logging
import unittest
from typing import Dict

from aspyx.di import injectable, on_init, on_destroy, inject_environment, inject, Factory, create, configuration, Environment, PostProcessor, factory
from di_import import ImportConfiguration, ImportedClass

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
class SamplePostProcessor(PostProcessor):
    def process(self, instance: object):
        pass #print(f"created a {instance}")

class Foo:
    pass

#@injectable()
class Baz:
    pass

@injectable()
class Bazong:
    def __init__(self, foo: Foo):
        pass

@injectable()
class Bar:
    def __init__(self, foo: Foo):
        self.foo = foo
        self.inited = False
        self.destroyed = False
        self.evironment = None

    @on_init()
    def init(self):
        self.inited = True

    @on_destroy()
    def destroy(self):
        self.destroyed = True

    @inject_environment()
    def initEnvironment(self, env: Environment):
        self.evironment = env

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

@configuration()
class SimpleConfiguration:
    # constructor

    def __init__(self):
        pass

    # create some beans

    @create()
    def create(self) -> Baz:
        return Baz()

@configuration(imports=[SimpleConfiguration, ImportConfiguration])
class Configuration:
    # constructor

    def __init__(self):
        pass

class TestInject(unittest.TestCase):

    def test_create(self):
        env = Environment(SimpleConfiguration)

        bar = env.get(Bar)
        baz = env.get(Baz)
        bazong = env.get(Bazong)
        foo = env.get(Foo)

        self.assertIsNotNone(bar)
        self.assertEqual(bar.inited, True)
        self.assertIs(bar.foo, foo)
        self.assertIs(bar.baz, baz)
        self.assertIs(bar.bazong, bazong)

    def test_singleton(self):
        env = Environment(SimpleConfiguration)

        bar = env.get(Bar)
        bar1 = env.get(Bar)

        self.assertIs(bar, bar1)

    def test_import_configurations(self):
        env = Environment(Configuration)

        imported = env.get(ImportedClass)

        self.assertIsNotNone(imported)

    def test_destroy(self):
        env = Environment(SimpleConfiguration)

        bar = env.get(Bar)

        env.destroy()

        self.assertEqual(bar.destroyed, True)

    def test_perfomance(self):
        env = Environment(SimpleConfiguration)

        start = time.perf_counter()
        for _ in range(1000000):
            bar = env.get(Bar)
        end = time.perf_counter()

        avg_ms = ((end - start) / 1000000) * 1000
        print(f"Average time per Bar creation: {avg_ms:.3f} ms")


if __name__ == '__main__':
   unittest.main()