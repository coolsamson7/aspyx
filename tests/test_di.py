from __future__ import annotations

import logging
import unittest
from typing import Dict

from aspyx.di import injectable, on_init, on_destroy, inject_environment, inject, Factory, create, configuration, Environment, PostProcessor, factory
from di_import import ImportConfiguration, ImportedClass
from sub_import import SubImportConfiguration, Sub

# not here

logging.basicConfig(level=logging.INFO)

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

    @on_init()
    def init(self):
        print("init bar")

    @on_destroy()
    def destroy(self):
        print("destroy bar")

    @inject_environment()
    def initEnvironment(self, env: Environment):
        print("set environment bar")

    @inject()
    def set(self, baz: Baz, bazong: Bazong) -> None:
        print("set bar.baz")
        pass

@factory()
class TestFactory(Factory[Foo]):
    __slots__ = []

    def __init__(self):
        pass

    def create(self) -> Foo:
        return Foo()

@configuration(imports=[ImportConfiguration])
class Configuration:
    # constructor

    def __init__(self):
        pass

    # create some beans

    @create()
    def create(self) -> Baz:
        return Baz()

class TestInject(unittest.TestCase):
    def test_1(self):
        env = Environment(Configuration)

        imported = env.get(ImportedClass)

        bar = env.get(Bar)
        foo = env.get(Foo)

        env2 = Environment(SubImportConfiguration, parent=env)

        sub = env2.get(Sub)

        env.shutdown()


if __name__ == '__main__':
   unittest.main()